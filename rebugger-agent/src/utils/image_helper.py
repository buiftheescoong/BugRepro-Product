import base64
import httpx
from src.utils.logger import get_logger

logger = get_logger("image_helper")

async def get_image_base64(image_source: str):
    """
    Chuyển đổi URL hoặc đường dẫn cục bộ thành chuỗi Base64
    """
    if not image_source:
        return None
    
    if image_source.startswith("http"):
        async with httpx.AsyncClient() as client:
            response = await client.get(image_source)
            if response.status_code == 200:
                return base64.b64encode(response.content).decode("utf-8")
            else:
                logger.error("Image download failed", extra={"data": {"url": image_source, "status_code": response.status_code}})
                return None

    try:
        with open(image_source, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error("Local file read failed", exc_info=True, extra={"data": {"path": image_source}})
        return None