"""Start the local API with an optional, hidden Qwen key prompt.

From apps/api: python -m app.dev_server
The key only lives in this server process and is never written to a file.
"""

import argparse
import getpass
import os
import sys

import uvicorn


REGION_BASE_URLS = {
    "beijing": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "singapore": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "us": "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    "hongkong": "https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local Knowledge Assistant API")
    parser.add_argument("--region", choices=REGION_BASE_URLS, help="API Key region")
    parser.add_argument("--without-model", action="store_true", help="Use retrieval only")
    args = parser.parse_args(argv)

    if not args.without_model:
        if not os.environ.get("DASHSCOPE_BASE_URL", "").strip():
            region = args.region
            if region is None:
                if not sys.stdin.isatty():
                    parser.error("Run in an interactive terminal to select the API Key region")
                selection = input("API Key region: 1 Beijing / 2 Singapore / 3 US / 4 Hong Kong: ").strip()
                region = {"1": "beijing", "2": "singapore", "3": "us", "4": "hongkong"}.get(selection)
            if region is None:
                parser.error("Select the region shown on the Model Studio API Key page")
            os.environ["DASHSCOPE_BASE_URL"] = REGION_BASE_URLS[region]
        if not os.environ.get("DASHSCOPE_API_KEY", "").strip():
            if not sys.stdin.isatty():
                parser.error("Run in an interactive terminal to enter the API key, or use --without-model")
            key = getpass.getpass("Qwen API Key (hidden, not saved): ").strip()
            if not key:
                parser.error("No API key entered; use --without-model for retrieval-only mode")
            os.environ["DASHSCOPE_API_KEY"] = key

    print("Open http://127.0.0.1:5173/?kbId=<your-kb-id> after starting the web server.")
    print("API logs show request paths and retrieval/answer status. Press Ctrl+C to stop.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
