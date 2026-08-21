from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("scenara_data.app:app", host="0.0.0.0", port=8010)
