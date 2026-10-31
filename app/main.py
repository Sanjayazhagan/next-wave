import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api import router as session_router
from app.assistant import Assistant
from app.browser import BrowserWorker, HttpBrowserWorker
from app.channels import ChannelError, RoutedChannel
from app.config import Settings
from app.conversation import ConversationContext
from app.events import EventLog
from app.graph.builder import build_graph
from app.graph.nodes import Deps
from app.language import LanguageService
from app.llm import ChatLlm
from app.planner import Planner
from app.plugins import Plugins, load_plugins
from app.privacy import router as privacy_router
from app.sessions import SessionManager, SessionStore
from app.skills import SkillStore
from app.standins import StubBrowser, StubExtractor
from app.telegram.channel import TelegramChannel
from app.telegram.client import TelegramClient
from app.telegram.webhook import router as telegram_router
from app.vault import FileStore, Vault, decode_master_key, derive_key
from app.whatsapp.channel import WhatsAppChannel
from app.whatsapp.client import WhatsAppClient
from app.whatsapp.dedupe import SeenMessages
from app.whatsapp.webhook import router as whatsapp_router

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    http: httpx.AsyncClient | None = None,
    browser: BrowserWorker | None = None,
    plugins: Plugins | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = http or httpx.AsyncClient(timeout=30)
        master_key = decode_master_key(settings.vault_key)

        seen = SeenMessages(settings.database_path)
        vault = Vault(settings.database_path, master_key)
        files = FileStore(settings.files_path, master_key)
        skills = SkillStore(settings.database_path)
        events = EventLog(settings.database_path)
        sessions = SessionStore(settings.database_path)
        language = LanguageService(settings, client)
        whatsapp = WhatsAppClient(settings, client)
        whatsapp_channel = WhatsAppChannel(whatsapp, language, files)

        telegram = None
        telegram_channel = None
        if settings.telegram_bot_token and settings.telegram_webhook_secret:
            telegram = TelegramClient(settings, client)
            telegram_channel = TelegramChannel(telegram, language, files)
        channel = RoutedChannel(whatsapp_channel, telegram_channel)

        loaded = plugins or load_plugins()
        if settings.use_standins and loaded.extraction is None:
            loaded.extraction = StubExtractor()
        worker = browser or (
            StubBrowser() if settings.use_standins else HttpBrowserWorker(settings, client)
        )

        settings.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(settings.checkpoint_path)
        # Checkpoints hold the profile and any OTP in flight, so encrypt them.
        checkpointer = AsyncSqliteSaver(
            connection,
            serde=EncryptedSerializer.from_pycryptodome_aes(
                key=derive_key(master_key, "checkpoints")
            ),
        )
        await checkpointer.setup()

        llm = ChatLlm(settings, client)
        deps = Deps(
            settings=settings,
            browser=worker,
            vault=vault,
            files=files,
            skills=skills,
            planner=Planner(llm, settings.final_submit_pattern),
            assistant=Assistant(llm),
            plugins=loaded,
            events=events,
            sessions=sessions,
        )
        manager = SessionManager(build_graph(deps, checkpointer), sessions, events, channel)

        def context(downloader) -> ConversationContext:
            return ConversationContext(
                settings, downloader, channel, language, files, sessions, manager
            )

        app.state.settings = settings
        app.state.seen = seen
        app.state.files = files
        app.state.vault = vault
        app.state.events = events
        app.state.sessions = sessions
        app.state.manager = manager
        app.state.whatsapp_context = context(whatsapp)
        app.state.telegram_client = telegram
        app.state.telegram_context = context(telegram) if telegram else None

        if telegram and settings.public_url:
            try:
                await telegram.set_webhook(
                    f"{settings.public_url.rstrip('/')}/telegram",
                    settings.telegram_webhook_secret,
                )
                log.info("Telegram webhook registered")
            except ChannelError as exc:
                log.error("Could not register the Telegram webhook: %s", exc)

        recovery = asyncio.create_task(manager.recover())
        yield
        recovery.cancel()
        await connection.close()
        for store in (seen, vault, skills, events, sessions):
            store.close()
        await client.aclose()

    logging.basicConfig(level=logging.INFO)
    # httpx logs full URLs at INFO, and Telegram's URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(title="GradientZero", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins.split(","),
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(whatsapp_router)
    app.include_router(telegram_router)
    app.include_router(session_router)
    app.include_router(privacy_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
