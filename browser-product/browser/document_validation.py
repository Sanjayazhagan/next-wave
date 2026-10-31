"""Validate prepared document bytes before exposing them to a browser."""
import io,re
from fastapi import HTTPException
def validate_document(raw,filename,mime):
    if len(raw)>1048576:raise HTTPException(413,'Prepared document exceeds 1 MB')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',filename):raise HTTPException(422,'Invalid document filename')
    if mime=='application/pdf':
        if not raw.startswith(b'%PDF-') or not filename.lower().endswith('.pdf'):raise HTTPException(422,'PDF signature/extension mismatch')
        return
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>20000000 or (mime,image.format) not in (('image/png','PNG'),('image/jpeg','JPEG')):raise ValueError()
            image.verify()
        if not filename.lower().endswith(('.png',) if mime=='image/png' else ('.jpg','.jpeg')):raise ValueError()
    except Exception:raise HTTPException(422,'Image signature, dimensions or extension invalid')
