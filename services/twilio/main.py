from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import random
import time
import uuid
import logging

app = FastAPI(title="Twilio Microservice")
logger = logging.getLogger("twilio")
logging.basicConfig(level=logging.INFO)

class SMSRequest(BaseModel):
    phone_number: str
    message: str

TWILIO_FAILURE_RATE = 0.05

@app.post("/send")
def send_sms(req: SMSRequest):
    min_delay = 0.1
    max_delay = 0.5
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

    if random.random() < TWILIO_FAILURE_RATE:
        error_codes = ["20003", "21211", "30008"]
        error_code = random.choice(error_codes)
        logger.warning(f"Simulated failure for {req.phone_number}: error {error_code}")
        raise HTTPException(status_code=503, detail=f"Twilio error {error_code} for {req.phone_number}")

    sid = f"SM{uuid.uuid4().hex[:32].upper()}"
    logger.info(f"SMS queued: {sid} -> {req.phone_number}")
    return {
        "provider": "TWILIO",
        "sid": sid,
        "phone_number": req.phone_number,
        "status": "queued",
        "direction": "outbound-api",
        "price": "-0.0079",
        "price_unit": "USD",
        "latency_ms": int(delay * 1000),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
