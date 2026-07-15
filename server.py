from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import html
import json
import os
import requests

latest_text = "まだ説明はありません"

HTML = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>専門用語サーバー AI版</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 24px; line-height: 1.6; }
    h1 { font-size: 30px; }
    textarea { width: 100%; height: 180px; font-size: 18px; padding: 12px; box-sizing: border-box; }
    button { font-size: 18px; padding: 12px 18px; margin-top: 12px; }
    .box { margin-top: 20px; padding: 16px; background: #f2f2f2; white-space: pre-wrap; font-size: 18px; }
  </style>
</head>
<body>
  <h1>専門用語サーバー AI版</h1>
  <p>文章を入れると、AIが難しいIT用語を探してROKIDへ送ります。</p>

  <form method="POST" action="/explain">
    <textarea name="text" placeholder="例：今日の会議でAPIとSDKとクラウドデプロイについて話します"></textarea>
    <br>
    <button type="submit">AIで説明する</button>
  </form>

  <p>ROKIDに表示される内容:</p>
  <div class="box">{latest}</div>
</body>
</html>"""

def ai_explain(user_text):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not api_key:
        return "OpenAI APIキーが入っていません\nRenderのEnvironmentで OPENAI_API_KEY を設定してください"

    prompt = f"""
あなたは会話中の専門用語サポートです。
次の文章から、一般の人に難しいIT用語だけを最大3つ選び、
ROKIDスマートグラスで読めるように短く説明してください。

条件:
- 日本語
- 1語につき1行
- 形式: 用語：やさしい説明
- 長くしない
- 難しい言葉がなければ「まだ説明はありません」と返す

文章:
{user_text}
"""

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 220,
            },
            timeout=30,
        )

        if res.status_code != 200:
            return f"OpenAIエラー {res.status_code}\n{res.text[:300]}"

        data = res.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"サーバーエラー: {e}"

class Handler(BaseHTTPRequestHandler):
    def _send(self, body, content_type="text/html; charset=utf-8"):
        body_bytes = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        global latest_text

        if self.path.startswith("/latest"):
            body = json.dumps({"text": latest_text}, ensure_ascii=False)
            self._send(body, "application/json; charset=utf-8")
            return

        if self.path.startswith("/text"):
            self._send(latest_text, "text/plain; charset=utf-8")
            return

        safe_latest = html.escape(latest_text)
        self._send(HTML.replace("{latest}", safe_latest))

    def do_POST(self):
        global latest_text

        if self.path.startswith("/explain"):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            form = parse_qs(raw)
            user_text = form.get("text", [""])[0].strip()

            if not user_text:
                latest_text = "文章が空です"
            else:
                latest_text = ai_explain(user_text)

            safe_latest = html.escape(latest_text)
            self._send(HTML.replace("{latest}", safe_latest))
            return

        self.send_response(404)
        self.end_headers()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Server running on port {port}")
    server.serve_forever()
