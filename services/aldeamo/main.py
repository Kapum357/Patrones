from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import time
import uuid
import logging

app = FastAPI(title="Aldeamo Microservice")
logger = logging.getLogger("aldeamo")
logging.basicConfig(level=logging.INFO)

class SMSRequest(BaseModel):
    phone_number: str
    message: str

ALDEAMO_FAILURE_RATE = 0.5

@app.post("/send")
def send_sms(req: SMSRequest):
    min_delay = 0.05
    max_delay = 0.3
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

    if random.random() < ALDEAMO_FAILURE_RATE:
        error_codes = ["TIMEOUT", "SERVICE_UNAVAILABLE", "RATE_LIMIT_EXCEEDED", "INVALID_DESTINATION"]
        error_code = random.choice(error_codes)
        logger.warning(f"Simulated failure for {req.phone_number}: {error_code}")
        raise HTTPException(status_code=503, detail=f"Aldeamo API error [{error_code}] for {req.phone_number}")

    message_id = f"ALG-{uuid.uuid4().hex[:12].upper()}"
    logger.info(f"SMS delivered: {message_id} -> {req.phone_number}")
    return {
        "provider": "ALDEAMO",
        "message_id": message_id,
        "phone_number": req.phone_number,
        "status": "DELIVERED",
        "segments": max(1, len(req.message) // 160 + 1),
        "latency_ms": int(delay * 1000),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
