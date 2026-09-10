from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse


app = FastAPI()

@app.post("/shorten")
async def shorten_url(request: Request):
    try:
        data = await request.json()
        original_url = data.get("url")
        if not original_url:
            raise HTTPException(status_code=400, detail="URL is required")
        # i want to use postgresql to store the original_url and shortened_url
        # Example placeholder logic - replace with actual PostgreSQL operations
        shortened_url = f"http://short.url/{hash(original_url) % 1000000}"

        return JSONResponse(content={"original_url": original_url, "shortened_url": shortened_url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/{shortened_path}")
async def redirect_to_original(shortened_path: str):
    try:
        # Example placeholder logic - replace with actual PostgreSQL operations
        # Here you would query your PostgreSQL database to find the original URL based on the shortened path
        original_url = f"http://example.com/original/{shortened_path}"  # Placeholder for demonstration

        if not original_url:
            raise HTTPException(status_code=404, detail="Shortened URL not found")

        return JSONResponse(content={"original_url": original_url})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))