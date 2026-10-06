"""手工联调：验证网页聊天的实例隔离（不在 CI 里跑，需要真实 Ollama）。

用法::

    # 终端 A：单独启动网页聊天服务（不需要桌面端主程序、不需要 Qt）
    python -m stlibs.mproc.onlinechat

    # 终端 B：跑这个脚本
    python tools/manual/probe_onlinechat.py glm4:latest

预期结果：

* 两个不同 session 各自让 ``instances_created`` 递增（= 新实例）；
* 同一 session 再发消息时 ``instances_created`` 不变、该 session 的 ``turns`` 递增
  （= 复用实例、记忆独立）；
* ``/api/reset`` 只丢掉指定 session，其它 session 不受影响。
"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:52493"


def post(path, payload=None, timeout=180):
    data = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "glm4:latest"

    try:
        post("/api/health")
    except (urllib.error.URLError, ConnectionError):
        print(f"连不上 {BASE} —— 先另开一个终端跑：python -m stlibs.mproc.onlinechat")
        return 1

    print("== /api/getmodellist ==")
    _, payload = post("/api/getmodellist")
    for item in payload["models"]:
        print(f"   {item['value']:<45} label={item['label']:<20} backend={item['backend']}")

    print("\n== 参数校验（都应该是 400）==")
    print("   未知模型 :", post("/api/chat", {"model": "nope", "question": "hi"})[0])
    print("   空问题   :", post("/api/chat", {"model": model, "question": "   "})[0])

    print("\n== 池状态（发消息前）==")
    print("  ", post("/api/status")[1]["pool"])

    print(f"\n== 用 {model} 给两个不同 session 各发一条（instances_created 应 +2）==")
    for session_id in ("manual-a", "manual-b"):
        status, payload = post("/api/chat", {"model": model, "question": "用一句话自我介绍", "session_id": session_id})
        answer = payload.get("answer", payload)
        print(f"   [{session_id}] HTTP {status}: {str(answer)[:60]!r}")
        print("   pool ->", post("/api/status")[1]["pool"])

    print("\n== 同一个 session 再发一条（instances_created 不变、turns 递增）==")
    post("/api/chat", {"model": model, "question": "刚才我问了什么？", "session_id": "manual-a"})
    print("   pool ->", post("/api/status")[1]["pool"])

    print("\n== /api/reset 丢掉 session-a（另一个 session 不受影响）==")
    print("   ", post("/api/reset", {"session_id": "manual-a"}))
    print("   pool ->", post("/api/status")[1]["pool"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
