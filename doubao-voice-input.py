#!/usr/bin/env python3
import argparse
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import requests

BASE = "https://openspeech.bytedance.com/api/v3/auc/bigmodel"
RESOURCE_ID = "volc.seedasr.auc"


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def headers(request_id, api_key):
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": "-1",
    }


def submit(audio_path, api_key, uid):
    request_id = str(uuid.uuid4())
    with open(audio_path, "rb") as f:
        audio = base64.b64encode(f.read()).decode()
    payload = {
        "user": {"uid": uid},
        "audio": {
            "data": audio,
            "format": "wav",
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": False,
            "enable_ddc": False,
            "enable_speaker_info": False,
            "enable_channel_split": False,
            "show_utterances": False,
            "vad_segment": False,
            "sensitive_words_filter": "",
        },
    }
    r = requests.post(f"{BASE}/submit", headers=headers(request_id, api_key), json=payload, timeout=60)
    if r.headers.get("x-api-status-code") not in (None, "20000000") or r.status_code >= 300:
        die(f"submit failed: http={r.status_code} status={r.headers.get('x-api-status-code')} body={r.text}")
    return request_id


def extract_text(data):
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    for key in ("text", "result", "utterance_text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    utterances = data.get("utterances")
    if isinstance(utterances, list):
        text = "".join(extract_text(x) for x in utterances)
        if text.strip():
            return text.strip()
    for value in data.values():
        text = extract_text(value)
        if text.strip():
            return text.strip()
    return ""


def query(request_id, api_key, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.post(f"{BASE}/query", headers=headers(request_id, api_key), json={}, timeout=30)
        status = r.headers.get("x-api-status-code")
        if status == "20000000":
            text = extract_text(r.json() if r.text else {})
            if text:
                return text
        elif status not in ("20000001", "20000002", "20000003", None):
            die(f"query failed: http={r.status_code} status={status} body={r.text}")
        time.sleep(1)
    die("query timed out")


def record(path, seconds, device):
    cmd = ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(seconds), path]
    subprocess.run(cmd, check=True)


def can_show_ui(no_ui):
    return not no_ui and shutil.which("yad") and (os.getenv("WAYLAND_DISPLAY") or os.getenv("DISPLAY"))


def show_status(text, no_ui=False, timeout=None):
    if not can_show_ui(no_ui):
        return None
    cmd = [
        "yad",
        "--class=doubao-voice-input",
        "--title=豆包语音",
        f"--text={text}",
        "--no-buttons",
        "--undecorated",
        "--on-top",
        "--skip-taskbar",
        "--center",
        "--width=260",
        "--height=92",
    ]
    if timeout:
        cmd += [f"--timeout={timeout}", "--timeout-indicator=none"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return proc.pid


def close_status(pid):
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def api_key_or_die(no_ui):
    api_key = os.getenv("DOUBAO_ASR_API_KEY")
    if not api_key:
        show_status("缺少 API Key", no_ui, timeout=2)
        die("set DOUBAO_ASR_API_KEY first")
    return api_key


def state_path():
    runtime_dir = os.getenv("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime_dir, "doubao-voice-input.json")


def start_recording(device, no_ui):
    state = state_path()
    if os.path.exists(state):
        die("recording is already running")
    audio = tempfile.NamedTemporaryFile(prefix="doubao-voice-input-", suffix=".wav", delete=False)
    audio.close()
    cmd = ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", "16000", "-c", "1", audio.name]
    proc = subprocess.Popen(cmd, start_new_session=True)
    with open(state, "w") as f:
        json.dump({"pid": proc.pid, "audio": audio.name, "status_pid": show_status("输入中", no_ui)}, f)


def stop_recording():
    state = state_path()
    if not os.path.exists(state):
        die("no recording is running")
    with open(state) as f:
        data = json.load(f)
    os.remove(state)
    close_status(data.get("status_pid"))
    os.killpg(data["pid"], signal.SIGINT)
    for _ in range(50):
        try:
            os.kill(data["pid"], 0)
            time.sleep(0.1)
        except ProcessLookupError:
            break
    return data["audio"]


def transcribe_and_type(audio_path, api_key, uid, timeout, no_type, no_ui):
    status_pid = show_status("等待中", no_ui)
    try:
        text = query(submit(audio_path, api_key, uid), api_key, timeout)
    finally:
        close_status(status_pid)
        try:
            os.remove(audio_path)
        except FileNotFoundError:
            pass
    print(text)
    if not no_type and text:
        status_pid = show_status("写入中", no_ui)
        try:
            subprocess.run(["wtype", text], check=True)
        finally:
            close_status(status_pid)
    show_status("完成", no_ui, timeout=1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-s", "--seconds", type=int, default=5)
    p.add_argument("-d", "--device", default="default")
    p.add_argument("--uid", default=os.getenv("USER", "nixos"))
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--no-type", action="store_true", help="print only; do not type into the active Wayland window")
    p.add_argument("--no-ui", action="store_true", help="disable the floating status window")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--start", action="store_true", help="start recording and exit")
    mode.add_argument("--stop", action="store_true", help="stop recording, transcribe, and type")
    args = p.parse_args()

    if args.start:
        start_recording(args.device, args.no_ui)
        return

    if args.stop:
        audio = stop_recording()
        try:
            api_key = api_key_or_die(args.no_ui)
        except SystemExit:
            try:
                os.remove(audio)
            except FileNotFoundError:
                pass
            raise
        transcribe_and_type(audio, api_key, args.uid, args.timeout, args.no_type, args.no_ui)
        return

    api_key = api_key_or_die(args.no_ui)
    audio = tempfile.NamedTemporaryFile(prefix="doubao-voice-input-", suffix=".wav", delete=False)
    audio.close()
    status_pid = show_status("输入中", args.no_ui)
    try:
        record(audio.name, args.seconds, args.device)
    finally:
        close_status(status_pid)
    transcribe_and_type(audio.name, api_key, args.uid, args.timeout, args.no_type, args.no_ui)


if __name__ == "__main__":
    main()
