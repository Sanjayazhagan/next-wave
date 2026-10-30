"""Reviewed portal manifest boundary. Unverified official flows stay disabled."""
from dataclasses import dataclass
from typing import Protocol


class PortalAdapter(Protocol):
    id: str
    version: str
    fields: tuple
    async def phase(self, page) -> str: ...
    async def review(self, page) -> dict: ...


class MockScholarship:
    id = 'mock-scholarship'
    version = '1.0'
    fields = (
        ('Student name','Full legal name','student_name'),
        ('Course','Programme','course'),
        ('Annual family income','Household annual earnings','income'),
        ('State','Home state','state'),
        ('Community category','Category','category'),
    )

    async def phase(self, page):
        return await page.locator('#main').get_attribute('data-stage') or 'unknown'

    async def review(self, page):
        return await page.evaluate('window.demoReviewData()')


MOCK = MockScholarship()
CATALOG = [
    {'id':MOCK.id,'version':MOCK.version,'enabled':True,'mode':'demo','application_flow':True,'upload':{'mime':'application/pdf','max_bytes':1048576}},
    {'id':'nsp','url':'https://scholarships.gov.in/Students','enabled':False,'mode':'official_public','application_flow':False,'blocker':'Authenticated fields, permission and applicant access not verified'},
    {'id':'tn-esevai','url':'https://tnesevai.tn.gov.in/','enabled':False,'mode':'official_public','application_flow':False,'blocker':'Service/role, permission and authenticated form not verified'},
    {'id':'tn-welfare','url':'https://bcmbcmw.tn.gov.in/welfschemes.htm','enabled':False,'mode':'official_public','application_flow':False,'blocker':'Information source; application destination not verified'},
    {'id':'myscheme','url':'https://www.myscheme.gov.in/','enabled':False,'mode':'official_public','application_flow':False,'blocker':'Discovery source; not a universal application endpoint'},
    {'id':'digilocker','url':'https://www.digilocker.gov.in/','enabled':False,'mode':'official_public','application_flow':False,'blocker':'Document service; not a scholarship application adapter'},
]


def resolve(portal_id):
    if portal_id != MOCK.id:
        raise ValueError('Portal has no verified, enabled application adapter')
    return MOCK
