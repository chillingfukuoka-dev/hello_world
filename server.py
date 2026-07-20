import os
import threading

import requests
from flask import Flask, Response, jsonify, request


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

latest_text = "まだ説明はありません"
latest_lock = threading.Lock()
NO_TERMS = "IT用語は見つかりませんでした"
TRANSCRIPTION_CONTEXT_MARKER = "直前の会話:"
TRANSCRIPTION_PROMPT_LEAKS = (
    "日本語のIT会議",
    "文脈に合う自然な日本語",
    "IT用語を正確に文字起こし",
)
SILENCE_HALLUCINATIONS = (
    "ご視聴ありがとうございました",
    "字幕をご覧いただきありがとうございました",
)


HTML = r"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ツウジルAI</title>
  <style>
    :root {
      color-scheme: light;
      --forest: #355c45;
      --forest-dark: #244232;
      --sage: #8aa27d;
      --sage-pale: #e4eadf;
      --coffee: #6b4d3b;
      --terracotta: #a86645;
      --paper: #f5f1e8;
      --surface: #fffdf8;
      --line: #d9d0c2;
      --ink: #26332a;
      --muted: #667066;
      --forest: #5c7a5e;
      --forest-dark: #2d3f2e;
      --sage: #7a8f7b;
      --sage-pale: #ebe5db;
      --coffee: #2d3f2e;
      --terracotta: #2d3f2e;
      --paper: #f2ede4;
      --surface: #f8f5ef;
      --line: rgba(92, 122, 94, .20);
      --ink: #2d3f2e;
      --muted: #7a8f7b;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", sans-serif;
      margin: 0;
      min-height: 100vh;
      padding: 24px 18px 48px;
      color: var(--ink);
      background: var(--paper);
    }
    main {
      max-width: 680px;
      margin: 0 auto;
      padding: 28px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-top: 6px solid var(--forest);
      border-radius: 8px;
    }
    h1 { font-size: 32px; margin: 4px 0 12px; color: var(--forest-dark); }
    p { line-height: 1.6; }
    textarea {
      width: 100%;
      min-height: 150px;
      padding: 14px;
      font-size: 18px;
      color: var(--ink);
      background: #fbfaf5;
      border: 1px solid #b8c3b1;
      background: #ebe5db;
      border: 1px solid rgba(92, 122, 94, .20);
      border-radius: 8px;
      resize: vertical;
    }
    textarea:focus {
      outline: none;
      border-color: var(--forest);
      box-shadow: 0 0 0 3px rgba(53, 92, 69, .16);
      box-shadow: 0 0 0 3px rgba(92, 122, 94, .16);
    }
    textarea::placeholder { color: #8a8d84; }
    textarea::placeholder { color: #7a8f7b; }
    .buttons { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    button {
      min-height: 48px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px 18px;
      font-size: 18px;
      font-weight: 700;
      background: #eee8df;
      color: #463529;
      background: #ebe5db;
      color: #2d3f2e;
      cursor: pointer;
    }
    button:hover { filter: brightness(.96); }
    button.primary { background: var(--forest); border-color: var(--forest); color: white; }
    button.stop { background: var(--terracotta); border-color: var(--terracotta); color: white; }
    #send { background: var(--coffee); border-color: var(--coffee); color: white; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    #status {
      min-height: 24px;
      margin-top: 18px;
      padding: 10px 12px;
      color: var(--forest-dark);
      font-weight: 700;
      background: var(--sage-pale);
      border-left: 4px solid var(--sage);
      border-radius: 4px;
    }
    .output-title { color: var(--coffee); font-weight: 700; }
    #latest {
      font-size: 20px;
      line-height: 1.55;
      white-space: pre-wrap;
      background: #eef1e8;
      border: 1px solid #cad3c3;
      background: #ebe5db;
      border: 1px solid rgba(92, 122, 94, .20);
      border-left: 5px solid var(--coffee);
      border-radius: 6px;
      padding: 16px;
      min-height: 64px;
    }
    .note { color: var(--muted); font-size: 14px; }
    @media (max-width: 520px) {
      body { padding: 12px 10px 32px; }
      main { padding: 20px 16px; }
      h1 { font-size: 28px; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
<main>
  <h1>ツウジルAI</h1>
  <p>文章または会話から、難しいIT用語を探してROKIDへ送ります。</p>

  <textarea id="term" placeholder="例：今日の会議でAPIとSDKとクラウドデプロイについて話します" autocomplete="off"></textarea>

  <div class="buttons">
    <button id="listen" class="primary">聞き取り開始</button>
    <button id="send">入力文をAIで説明</button>
  </div>

  <p id="status">待機中</p>
    <p class="note">聞き取り中は、声が入った約10秒分だけを送信します。無音は送信しません。</p>

    <p class="output-title">ROKIDに表示される内容：</p>
  <pre id="latest">読み込み中...</pre>

  <script>
    const input = document.getElementById("term");
    const statusText = document.getElementById("status");
    const listenButton = document.getElementById("listen");
    const sendButton = document.getElementById("send");
    const latestBox = document.getElementById("latest");

const CHUNK_MS = 10000;
const VOICE_RMS_THRESHOLD = 0.035;
const VOICE_FRAME_COUNT = 6;
const TRANSCRIPTION_CONTEXT_MARKER = "直前の会話:";
const TRANSCRIPTION_PROMPT_MARKERS = [
  "日本語のIT会議",
  "文脈に合う自然な日本語",
  "IT用語を正確に文字起こし"
];
let listening = false;
    let mediaStream = null;
    let recorder = null;
    let stopTimer = null;
    let uploadQueue = Promise.resolve();
    let audioContext = null;
    let audioSource = null;
    let analyser = null;
    let lastTranscript = "";

    async function loadLatest() {
      try {
        const response = await fetch("/latest", {cache: "no-store"});
        const data = await response.json();
        latestBox.textContent = data.text;
      } catch (error) {
        latestBox.textContent = "サーバーとの通信を確認中...";
      }
    }

    function chooseMimeType() {
      const candidates = [
        "audio/mp4",
        "audio/webm;codecs=opus",
        "audio/webm"
      ];
      for (const type of candidates) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported(type)) return type;
      }
      return "";
    }

function cleanDisplayedTranscript(text) {
  let cleaned = String(text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "";

  const markerIndex = cleaned.lastIndexOf(TRANSCRIPTION_CONTEXT_MARKER);
  if (markerIndex >= 0) {
    cleaned = cleaned.slice(markerIndex + TRANSCRIPTION_CONTEXT_MARKER.length).trim();
  }

  if (TRANSCRIPTION_PROMPT_MARKERS.some((marker) => cleaned.includes(marker))) {
    return "";
  }
  return cleaned;
}

function appendTranscript(text) {
  const cleaned = cleanDisplayedTranscript(text);
  if (!cleaned || cleaned === lastTranscript) return;
      lastTranscript = cleaned;
      const current = input.value.trim();
      input.value = (current ? current + "\n" : "") + cleaned;
      if (input.value.length > 1800) input.value = input.value.slice(-1800);
      input.scrollTop = input.scrollHeight;
    }

    async function uploadAudio(blob, mimeType) {
      statusText.textContent = listening ? "聞き取り中・AI確認中..." : "最後の音声をAI確認中...";
      const extension = mimeType.includes("webm") ? "webm" : "m4a";
      const form = new FormData();
      form.append("audio", blob, `speech.${extension}`);

      const response = await fetch("/transcribe", {method: "POST", body: form});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "音声の送信に失敗しました");

      appendTranscript(data.transcript || "");
      if (data.updated) {
        statusText.textContent = "IT用語をROKIDへ送りました";
      } else if (data.transcript) {
        statusText.textContent = "この部分には難しいIT用語がありませんでした";
      } else {
        statusText.textContent = "音声が聞き取れませんでした";
      }
      await loadLatest();
    }

    function recordNextChunk() {
      if (!listening || !mediaStream) return;

      const mimeType = chooseMimeType();
      const options = mimeType ? {mimeType} : undefined;
      const chunks = [];
      let voiceFrames = 0;
      let levelTimer = null;
      recorder = options
        ? new MediaRecorder(mediaStream, options)
        : new MediaRecorder(mediaStream);

      if (analyser) {
        const levels = new Uint8Array(analyser.fftSize);
        levelTimer = setInterval(() => {
          analyser.getByteTimeDomainData(levels);
          let sumSquares = 0;
          for (let index = 0; index < levels.length; index += 1) {
            const normalized = (levels[index] - 128) / 128;
            sumSquares += normalized * normalized;
          }
          const rms = Math.sqrt(sumSquares / levels.length);
          if (rms >= VOICE_RMS_THRESHOLD) voiceFrames += 1;
        }, 100);
      }

      recorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };

      recorder.onerror = () => {
        statusText.textContent = "録音エラー。もう一度開始してください";
        stopListening();
      };

      recorder.onstop = () => {
        clearTimeout(stopTimer);
        if (levelTimer) clearInterval(levelTimer);
        const actualType = recorder.mimeType || mimeType || "audio/mp4";
        const blob = new Blob(chunks, {type: actualType});

        if (listening) setTimeout(recordNextChunk, 100);
        if (blob.size > 1000 && (!analyser || voiceFrames >= VOICE_FRAME_COUNT)) {
          uploadQueue = uploadQueue
            .then(() => uploadAudio(blob, actualType))
            .catch(error => { statusText.textContent = error.message; });
        } else if (listening) {
          statusText.textContent = "聞き取り中（音声待ち）";
        }

        if (!listening) closeMicrophone();
      };

      recorder.start();
      statusText.textContent = "聞き取り中...";
      stopTimer = setTimeout(() => {
        if (recorder && recorder.state === "recording") recorder.stop();
      }, CHUNK_MS);
    }

    async function startListening() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
        statusText.textContent = "このブラウザは音声入力に対応していません";
        return;
      }

      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1
          }
        });
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
          audioContext = new AudioContextClass();
          audioSource = audioContext.createMediaStreamSource(mediaStream);
          analyser = audioContext.createAnalyser();
          analyser.fftSize = 1024;
          audioSource.connect(analyser);
        }
        listening = true;
        listenButton.textContent = "聞き取り停止";
        listenButton.classList.remove("primary");
        listenButton.classList.add("stop");
        recordNextChunk();
      } catch (error) {
        statusText.textContent = "マイクの使用を許可してください";
      }
    }

    function closeMicrophone() {
      if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());
      if (audioSource) audioSource.disconnect();
      if (audioContext && audioContext.state !== "closed") audioContext.close();
      mediaStream = null;
      recorder = null;
      audioContext = null;
      audioSource = null;
      analyser = null;
    }

    function stopListening() {
      listening = false;
      clearTimeout(stopTimer);
      listenButton.textContent = "聞き取り開始";
      listenButton.classList.add("primary");
      listenButton.classList.remove("stop");
      statusText.textContent = "停止しました";
      if (recorder && recorder.state === "recording") recorder.stop();
      else closeMicrophone();
    }

    listenButton.addEventListener("click", () => {
      if (listening) stopListening();
      else startListening();
    });

    sendButton.addEventListener("click", async () => {
      const text = input.value.trim();
      if (!text) {
        statusText.textContent = "文章を入力してください";
        return;
      }

      sendButton.disabled = true;
      statusText.textContent = "AIに確認中...";
      try {
        const response = await fetch("/explain", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "送信に失敗しました");
        statusText.textContent = data.updated ? "ROKIDへ送りました" : NO_TERMS;
        await loadLatest();
      } catch (error) {
        statusText.textContent = error.message;
      } finally {
        sendButton.disabled = false;
      }
    });

    const NO_TERMS = "IT用語は見つかりませんでした";
    loadLatest();
    setInterval(loadLatest, 1500);
  </script>
</main>
</body>
</html>
"""


class OpenAIError(Exception):
    pass


def api_key():
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not value:
        raise OpenAIError("OpenAI APIキーが入っていません")
    return value


def openai_error(response):
    try:
        message = response.json().get("error", {}).get("message", "")
    except ValueError:
        message = response.text[:200]

    if response.status_code == 401:
        return "OpenAI APIキーを確認してください"
    if response.status_code == 429:
        return "OpenAIの残高または利用上限を確認してください"
    return f"OpenAIエラー {response.status_code}: {message[:160]}"


def explain_with_openai(text):
    prompt = f"""
あなたはIT会議の会話サポートAIです。
次の発言から、IT初心者がつまずきそうなIT専門用語を最大2個選び、短く説明してください。

ルール:
- IT、Web、アプリ、AI、クラウド、開発、ネットワーク、セキュリティの用語を優先
- 1語につき1行
- 形式は「用語：やさしい説明」
- 1行は全体で26文字程度まで
- 同じ意味の用語は1個にまとめる
- 該当語がなければ「{NO_TERMS}」だけを返す
- 前置き、箇条書き記号、感想は不要

発言:
{text}
""".strip()

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key()}"},
        json={
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": "IT用語を初心者向けの短い日本語で説明します。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 180,
        },
        timeout=45,
    )
    if not response.ok:
        raise OpenAIError(openai_error(response))

    result = response.json()["choices"][0]["message"]["content"].strip()
    return result or NO_TERMS


def clean_transcript(text):
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""

    marker_index = cleaned.rfind(TRANSCRIPTION_CONTEXT_MARKER)
    if marker_index >= 0:
        cleaned = cleaned[marker_index + len(TRANSCRIPTION_CONTEXT_MARKER):].strip()

    if not cleaned:
        return ""
    if any(marker in cleaned for marker in TRANSCRIPTION_PROMPT_LEAKS):
        return ""
    if any(phrase in cleaned for phrase in SILENCE_HALLUCINATIONS):
        return ""
    return cleaned


def transcribe_with_openai(audio_file):
    mime_type = audio_file.mimetype or "audio/mp4"
    filename = audio_file.filename or ("speech.webm" if "webm" in mime_type else "speech.m4a")
    audio_bytes = audio_file.read()
    if len(audio_bytes) < 1000:
        return ""

    # Instruction-like prompts can be echoed into short transcription results.
    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key()}"},
        files={"file": (filename, audio_bytes, mime_type)},
        data={
            "model": os.environ.get("OPENAI_TRANSCRIBE_MODEL", "whisper-1"),
            "language": "ja",
        },
        timeout=60,
    )
    if not response.ok:
        raise OpenAIError(openai_error(response))

    return clean_transcript(response.json().get("text", ""))


def set_latest(text):
    global latest_text
    with latest_lock:
        latest_text = text


def get_latest():
    with latest_lock:
        return latest_text


@app.after_request
def add_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return Response(HTML, content_type="text/html; charset=utf-8")


@app.get("/latest")
def latest():
    return jsonify(text=get_latest())


@app.get("/text")
def text_only():
    return Response(get_latest(), content_type="text/plain; charset=utf-8")


@app.post("/explain")
def explain():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify(error="文章を入力してください"), 400

    try:
        explanation = explain_with_openai(text)
        updated = explanation != NO_TERMS
        if updated:
            set_latest(explanation)
        return jsonify(explanation=explanation, updated=updated, text=get_latest())
    except OpenAIError as error:
        return jsonify(error=str(error)), 502


@app.post("/transcribe")
def transcribe():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify(error="音声ファイルがありません"), 400

    try:
        transcript = transcribe_with_openai(audio)
        if not transcript:
            return jsonify(transcript="", explanation="", updated=False, text=get_latest())

        explanation = explain_with_openai(transcript)
        updated = explanation != NO_TERMS
        if updated:
            set_latest(explanation)
        return jsonify(
            transcript=transcript,
            explanation=explanation,
            updated=updated,
            text=get_latest(),
        )
    except OpenAIError as error:
        return jsonify(error=str(error)), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    app.run(host="0.0.0.0", port=port, threaded=True)
