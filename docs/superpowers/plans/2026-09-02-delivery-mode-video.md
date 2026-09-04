# 배달(DELIVERING) 모드 — 시연 영상용 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "이거 윤지영 교수님한테 가져다줘" 한마디로 로봇이 **배달 확인 → 배달 출발 멘트 → 무음 도착 → 앱 알림 1회**까지 가고, 화장실 안내의 대기 수락 멘트에 좌우 안내가 붙게 한다. 2026-09-04 촬영용 일회 브랜치.

**Architecture:** 배달은 안내(navigate)와 **같은 확인 흐름**을 탄다 — 의도 이름만 `deliver` 로 다르다. 음성이 `deliver` 를 만들어 "OO로 배달할까요?" 로 되묻고, "그래"는 LLM 없이 확정한다. 미션은 `State.DELIVERING` 으로 달리고, 도착하면 **말 대신** `DeliveryDone` 액션을 내며, 노드가 그것을 기존 배관 `/vica_goal_event` 에 `delivery_succeeded` 로 싣는다. 앱은 그 이벤트 하나에만 팝업을 띄운다. 앱은 미션 상태를 모른다(`RobotState.msg` 에 상태 필드 없음 — 그대로 둔다).

**Tech Stack:** Python 3.10 (pydantic·langchain, rclpy/ament_python), Flutter 3.44 (linux arm64 데스크톱 빌드), pytest, flutter test.

**Spec:** 결정 기록은 세션 메모리 `video-demo-script-and-delivery-2026-09-04` 와 이 문서 §0. 별도 spec 파일은 없다(사용자가 대화로 확정).

## §0 확정 대사표 (2026-09-02 사용자 결정 — 글자 그대로)

**A. 안내(화장실, category2=restroom)** — 3·4번은 지금 코드 그대로, 5번만 바뀐다.

| # | 사람 | 로봇 | 출처 |
| --- | --- | --- | --- |
| 1 | "비카야" | "네?" | 그대로 |
| 2 | "화장실로 가줘" | "화장실로 안내해드릴까요?" | YAML `confirm_prompt` (앱이 "으로" 로 저장한다 — 손으로 고침, [[app-hardcodes-destination-ments]]) |
| 3 | "그래" | "화장실로 안내를 시작합니다." | `MSG_START` 그대로 |
| 4 | *(도착)* | "화장실 앞에 도착했습니다. 다녀오시는 동안 여기서 기다릴까요?" | 그대로 |
| 5 | "그래" | **"네, 다녀오세요. 남자 화장실은 왼쪽, 여자 화장실은 오른쪽입니다."** | **신설 `MSG_WAIT_RESTROOM`** (Task 4) |

**B. 배달(윤지영 교수님 사무실, category2=professor_office)**

| # | 사람 | 로봇 | 출처 |
| --- | --- | --- | --- |
| 1 | "비카야" | "네?" | 그대로 |
| 2 | "이거 윤지영 교수님한테 가져다줘" | **"윤지영 교수님 사무실로 배달할까요?"** | 음성 `deliver_prompt()` (Task 2) |
| 3 | "그래" | **"윤지영 교수님 사무실로 배달을 시작합니다."** | 미션 `MSG_DELIVER_START` (Task 3) |
| 4 | *(도착)* | **무음** → 앱 팝업 "배달 완료" | `DeliveryDone` → `delivery_succeeded` (Task 3·5) |

## Global Constraints

- **커밋 금지가 걸려 있다** (2026-09-02 사용자: "내가 말하는 순간까지"). 각 Task 의 커밋 단계는 **사용자가 풀어 준 뒤에만** 실행한다. 풀리기 전엔 그 단계를 건너뛰고 다음 Task 로 간다 — 작업 트리에 쌓아 둔다.
- 브랜치: 네 저장소 모두 `video/demo-0904`. 원본 손상 걱정 불필요(일회용) — 단 **다른 브랜치로 체크아웃하지 않는다**.
- 멘트는 §0 글자 그대로. 새 멘트를 더 만들지 않는다(멘트 최소주의). 하드 긴급어(`멈춰·정지·스탑·스톱·안돼·위험해`)가 멘트에 들어가면 `test_spoken_text` 가 막는다.
- 시험 기준선(2026-09-02 실측): 미션 `341 passed, 1 skipped` · 음성 `440 passed`. 끝나면 이 수 + 신규 시험이어야 하고 **빨간 것 0**.
- 미션 패키지는 **symlink 설치가 아니다** (`install/.../site-packages/vica_mission_manager/` 실복사). 코드를 고치면 `colcon build --packages-select vica_mission_manager` 후 노드 재시작. 음성은 소스 실행이라 launch 재시작만. 앱은 `flutter build linux --release`.
- `vica_interfaces` 는 **재빌드 불필요** — `VicaIntent.msg` 의 `intent` 는 `string` 이라 값 추가는 주석만 바꾼다.
- 시험 명령 (작업공간 루트 기준):
  - 미션: `cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q`
  - 음성: `cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q`
  - 앱: `cd VICA_Supervisor && flutter test test/models/goal_event_test.dart && flutter analyze`

## 파일 지도

| 저장소 | 파일 | 무엇 |
| --- | --- | --- |
| 음성 | `src/schema.py` | `VicaIntentType` 에 `"deliver"` |
| 음성 | `src/destination_loader.py` | `deliver_prompt(dest)` 신설 |
| 음성 | `src/langchain_intent_parser.py` | 프롬프트·`_pending_deliver_destination`·지름길·`_finalize` |
| 음성 | `src/tts_queue.py` | 확정 deliver 는 음성이 침묵 |
| 음성 | `tests/test_deliver_intent.py` | 신규 |
| 미션 | `vica_mission_manager/mission_logic.py` | `State.DELIVERING`·`DeliveryDone`·`MSG_DELIVER_START`·`MSG_WAIT_RESTROOM`·게이트·전이 |
| 미션 | `vica_mission_manager/mission_manager_node.py` | `DeliveryDone` 실행·`is_moving`·라우팅 2곳 |
| 미션 | `test/test_delivery.py` | 신규 |
| 미션 | `test/test_arrival_dialog.py` | restroom 대기 멘트 기대값 수정 + 2건 추가 |
| 계약 | `vica_interfaces/msg/VicaIntent.msg` | 주석에 deliver 절 |
| 앱 | `lib/models/goal_event.dart` | `deliverySucceeded` + 팝업 문구 |
| 앱 | `lib/providers/supervisor_provider.dart` | 이벤트 switch 1줄 |
| 앱 | `test/models/goal_event_test.dart` | 1건 추가 |

---

### Task 1: 영상용 브랜치 4곳

**Files:** 없음 (git 만)

- [ ] **Step 1: 현재 상태 확인** — 작업 트리의 기존 변경(`vica_ros2_ws` 의 `urdf.rviz` M·maps 미추적)은 **건드리지 않는다**. 브랜치 생성은 그것을 그대로 데려간다.

```bash
cd /home/ji_w/VICA-smarthandle
for r in . vica-voice-llm vica_ros2_ws VICA_Supervisor; do echo "== $r: $(git -C $r branch --show-current)"; git -C $r status --short | head -3; done
```
Expected: 루트·ros2·앱 = `feat/app-ux-mode-split`, 음성 = `dev`.

- [ ] **Step 2: 브랜치 생성**

```bash
cd /home/ji_w/VICA-smarthandle
git switch -c video/demo-0904
git -C vica-voice-llm switch -c video/demo-0904
git -C vica_ros2_ws switch -c video/demo-0904
git -C VICA_Supervisor switch -c video/demo-0904
for r in . vica-voice-llm vica_ros2_ws VICA_Supervisor; do echo "$r → $(git -C $r branch --show-current)"; done
```
Expected: 네 줄 모두 `video/demo-0904`.

---

### Task 2: 음성 — `deliver` 의도

**Files:**
- Modify: `vica-voice-llm/src/schema.py:50-63`
- Modify: `vica-voice-llm/src/destination_loader.py` (`_josa_euro` 아래)
- Modify: `vica-voice-llm/src/langchain_intent_parser.py` (import·`_IntentDraft`·`_build_system_prompt`·`_pending_*`·`parse_intent`·`_finalize`)
- Modify: `vica-voice-llm/src/tts_queue.py:95-98`
- Create: `vica-voice-llm/tests/test_deliver_intent.py`

**Interfaces:**
- Produces: `destination_loader.deliver_prompt(dest: DestinationData) -> str` = `f"{name}{조사} 배달할까요?"`
- Produces: `langchain_intent_parser._pending_deliver_destination(history, destinations) -> DestinationData | None`
- Produces: `_finalize(..., pending_deliver: DestinationData | None = None)`
- Produces: `/vica/intent` 에 `intent="deliver"` 가 흐른다. 제안은 `need_confirm=True, reply=deliver_prompt`, 확정은 `need_confirm=False, reply="{name} 배달을 시작합니다."`(로그용, TTS 안 나감).

- [ ] **Step 1: 실패하는 시험 작성** — `vica-voice-llm/tests/test_deliver_intent.py`

```python
"""배달(deliver) 의도 — 시연 영상용 (2026-09-04).

"이거 OO한테 가져다줘" → LLM 이 deliver 로 분류 → 코드가 목적지를 매칭해
"OO로 배달할까요?" 로 되묻는다 → "그래" 는 LLM 없이 확정 deliver.
발화 규칙은 navigate 와 같다: 확인 질문은 음성이, 출발 멘트는 미션이 말한다.
LLM 실호출은 자동화하지 않으므로 초안 후처리(_finalize)와 지름길만 검증한다.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.destination_loader import deliver_prompt
from src.langchain_intent_parser import (
    _finalize, _IntentDraft, _pending_deliver_destination, parse_intent)
from src.schema import DestinationData
from src.tts_queue import request_for_intent

DEST = DestinationData(
    id="office_yoon", name="윤지영 교수님 사무실",
    aliases=["윤지영 교수님", "윤지영 교수님 방"],
    confirm_prompt="윤지영 교수님 사무실로 안내해드릴까요?",
)
RESTROOM = DestinationData(id="wc", name="화장실",
                           confirm_prompt="화장실로 안내해드릴까요?")


def test_deliver_prompt_uses_josa():
    assert deliver_prompt(DEST) == "윤지영 교수님 사무실로 배달할까요?"
    assert deliver_prompt(DestinationData(id="x", name="식당")) == "식당으로 배달할까요?"


class TestFinalizeDeliver:
    def test_matched_asks_delivery_confirm(self):
        draft = _IntentDraft(intent="deliver", destination_candidate="윤지영 교수님 사무실",
                             confidence=0.9)
        r = _finalize(draft, [DEST, RESTROOM], user_text="이거 윤지영 교수님한테 가져다줘")
        assert r.intent == "deliver"
        assert r.matched_destination_id == DEST.id
        assert r.need_confirm is True
        assert r.reply == "윤지영 교수님 사무실로 배달할까요?"

    def test_unmatched_becomes_clarify(self):
        draft = _IntentDraft(intent="deliver", destination_candidate="없는 곳", confidence=0.5)
        r = _finalize(draft, [DEST], user_text="이거 저기 가져다줘")
        assert r.intent == "clarify"
        assert r.reply   # 되묻는 말이 비면 소리로만 아는 사용자는 멈춘다

    def test_llm_confirmation_after_delivery_question(self):
        draft = _IntentDraft(intent="deliver", destination_candidate=DEST.name,
                             is_confirmation=True, confidence=0.9)
        r = _finalize(draft, [DEST], pending_deliver=DEST, user_text="부탁해")
        assert r.intent == "deliver"
        assert r.need_confirm is False
        assert r.matched_destination_id == DEST.id

    def test_llm_confirmation_without_pending_is_not_trusted(self):
        """확인 질문이 없었는데 LLM 이 is_confirmation=true 를 줘도 되묻는다."""
        draft = _IntentDraft(intent="deliver", destination_candidate=DEST.name,
                             is_confirmation=True, confidence=0.9)
        r = _finalize(draft, [DEST], user_text="윤지영 교수님한테 갖다줘")
        assert r.need_confirm is True


class TestShortcutAfterDeliveryQuestion:
    HISTORY = [HumanMessage("이거 윤지영 교수님한테 가져다줘"),
               AIMessage("윤지영 교수님 사무실로 배달할까요?")]

    def test_pending_detected(self):
        assert _pending_deliver_destination(self.HISTORY, [DEST]) is DEST
        assert _pending_deliver_destination(None, [DEST]) is None
        assert _pending_deliver_destination([], [DEST]) is None

    def test_affirm_confirms_deliver_without_llm(self):
        for word in ("그래", "네", "응", "응 부탁해"):
            r = parse_intent(word, [DEST], history=self.HISTORY)
            assert r.intent == "deliver", word
            assert r.matched_destination_id == DEST.id, word
            assert r.need_confirm is False, word
            assert "배달" in r.reply, word          # 로그용 — TTS 로는 안 나간다

    def test_deny_after_delivery_question(self):
        for word in ("아니", "아니요", "네 아니 아니"):
            r = parse_intent(word, [DEST], history=self.HISTORY)
            assert r.intent == "deny", word
            assert r.need_confirm is False, word

    def test_navigate_confirm_prompt_is_not_delivery_pending(self):
        """안내 확인 질문 뒤의 "그래" 는 종전대로 navigate 다 (회귀 방지)."""
        history = [HumanMessage("화장실 가자"), AIMessage(RESTROOM.confirm_prompt)]
        assert _pending_deliver_destination(history, [DEST, RESTROOM]) is None
        r = parse_intent("그래", [DEST, RESTROOM], history=history)
        assert r.intent == "navigate"


class TestSpeaker:
    class _Fake:
        def __init__(self, intent, reply, need_confirm):
            self.intent, self.reply, self.need_confirm = intent, reply, need_confirm
            self.safety_flag = "normal"

    def test_confirmed_deliver_is_silent_here(self):
        """출발 멘트는 게이트를 아는 미션이 말한다 — navigate 와 같은 규칙."""
        assert request_for_intent(self._Fake("deliver", "x 배달을 시작합니다.", False)) is None

    def test_delivery_question_is_spoken_here(self):
        q = "윤지영 교수님 사무실로 배달할까요?"
        assert request_for_intent(self._Fake("deliver", q, True)) == f"response:{q}"
```

- [ ] **Step 2: 실패 확인**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/test_deliver_intent.py -q 2>&1 | tail -3
```
Expected: `ImportError: cannot import name 'deliver_prompt'` (수집 단계 실패).

- [ ] **Step 3: `schema.py` — 의도 종류에 deliver**

`VicaIntentType = Literal[` 블록의 `"wait", "finish",` 줄 **다음**에 추가:

```python
    # 배달 (2026-09-02, 시연 영상용). navigate 와 같은 확인 흐름을 타되 사람이
    # 따라가지 않는다 — 미션이 DELIVERING 으로 달리고 도착을 말하지 않는다.
    # destination_candidate·matched_destination_id 를 navigate 처럼 채운다.
    "deliver",
```

- [ ] **Step 4: `destination_loader.py` — `deliver_prompt`**

`_josa_euro` 함수 정의 **바로 아래**, `_fill_defaults` **위**에 추가:

```python
def deliver_prompt(dest: DestinationData) -> str:
    """배달 확인 질문 — "OO로 배달할까요?" (deliver 의도, 시연용 2026-09-04).

    confirm_prompt 와 달리 YAML 에 두지 않고 이름으로만 만든다 — 대화 이력에서
    직전 질문을 되찾을 때(_pending_deliver_destination) 글자가 같아야 하므로
    생성 규칙은 이 한 곳뿐이어야 한다.
    """
    return f"{dest.name}{_josa_euro(dest.name)} 배달할까요?"
```

- [ ] **Step 5: `langchain_intent_parser.py` — import**

```python
from .destination_matcher import match_destination
```
바로 아래에:
```python
from .destination_loader import deliver_prompt
```

- [ ] **Step 6: `langchain_intent_parser.py` — `_IntentDraft` 설명 두 줄**

```python
    intent: VicaIntentType = Field(
        description="navigate / question / clarify / unknown / cancel / pause / resume / affirm / deny 중 하나"
    )
```
→
```python
    intent: VicaIntentType = Field(
        description="navigate / deliver / question / clarify / unknown / cancel / pause / resume / affirm / deny / wait / finish 중 하나"
    )
```
그리고
```python
        description="navigate 일 때, 목적지 목록의 name 중 가장 알맞은 하나. 없으면 null.",
```
→
```python
        description="navigate·deliver 일 때, 목적지 목록의 name 중 가장 알맞은 하나. 없으면 null.",
```

- [ ] **Step 7: `langchain_intent_parser.py` — 시스템 프롬프트 세 곳**

(a) `[intent 종류]` 의 `- navigate: ...` 줄 **다음**에 한 줄 추가:
```
- deliver: 물건을 어딘가로 가져다 달라는 요청 ("이거 윤지영 교수님한테 가져다줘", "이거 407호에 갖다줘", "안내소에 배달해줘"). 사람이 따라가지 않고 로봇 혼자 간다. destination_candidate 에 목적지 name 을 채워라 — 사람 이름이면 그 사람의 사무실.
```

(b) `[규칙]` 의
```
- navigate(destination_candidate 포함)·cancel·pause·resume·affirm·deny·wait·finish 로
```
→
```
- navigate·deliver(destination_candidate 포함)·cancel·pause·resume·affirm·deny·wait·finish 로
```

(c) `[멀티턴 대화]` 첫 항목(`… is_confirmation=true 로 답해라.`) **다음**에 한 줄:
```
- 직전에 로봇이 'OO로 배달할까요?'라고 물었고 사용자가 긍정하면: intent=deliver, destination_candidate=그 OO 목적지 name, is_confirmation=true.
```

- [ ] **Step 8: `langchain_intent_parser.py` — `_pending_deliver_destination`**

`_pending_confirm_destination` 함수 **바로 아래**에 추가:

```python
def _pending_deliver_destination(
    history: Optional[list[BaseMessage]], destinations: Sequence[DestinationData]
):
    """직전 AI 발화가 어떤 목적지의 배달 확인 질문이었으면 그 목적지를 돌려준다.

    확인 질문(confirm_prompt)과 글자가 다르므로 둘 중 하나만 걸린다.
    """
    if not history:
        return None
    last_ai = next((m for m in reversed(history) if isinstance(m, AIMessage)), None)
    if last_ai is None:
        return None
    for dest in destinations:
        if deliver_prompt(dest) == last_ai.content:
            return dest
    return None
```

- [ ] **Step 9: `langchain_intent_parser.py` — `parse_intent` 지름길**

`pending = _pending_confirm_destination(history, destinations)` 블록이 끝나는 곳 — 즉
```python
            return VicaIntent(
                intent="deny",
                confidence=1.0,
                reply="",
                need_confirm=False,
            )

    # 명백한 취소·일시정지 발화는 LLM 없이 직행한다 (0초, 오판 없음).
```
의 빈 줄 자리에 아래 블록을 넣는다(`# 명백한 취소…` 주석 **앞**):

```python
    # 배달 확인 질문("OO로 배달할까요?") 뒤의 짧은 답 — navigate 지름길과 같은
    # 규칙(첫 단어 긍정, 부정 토막 하나라도 있으면 fail-closed).
    pending_deliver = _pending_deliver_destination(history, destinations)
    if pending_deliver is not None:
        word = _normalize_short_reply(user_text)
        tokens = user_text.split()
        first = _normalize_short_reply(tokens[0]) if tokens else ""
        denied = (word in _NEGATIVES
                  or any(_normalize_short_reply(t) in _NEGATIVES for t in tokens))
        if not denied and (word in _SOLO_AFFIRMATIVES or first in _AFFIRMATIVES):
            return VicaIntent(
                intent="deliver",
                destination_candidate=pending_deliver.name,
                matched_destination_id=pending_deliver.id,
                confidence=1.0,
                # 로그·기록용. TTS 로 안 나간다 — 출발 멘트는 미션 몫(tts_queue).
                reply=f"{pending_deliver.name} 배달을 시작합니다.",
                need_confirm=False,
                safety_flag="normal",
            )
        if denied:
            return VicaIntent(intent="deny", confidence=1.0, reply="",
                              need_confirm=False)

```

그리고 함수 끝의
```python
    return _finalize(draft, destinations, pending=pending,
                     pending_command=pending_command, user_text=user_text)
```
→
```python
    return _finalize(draft, destinations, pending=pending,
                     pending_command=pending_command, user_text=user_text,
                     pending_deliver=pending_deliver)
```

- [ ] **Step 10: `langchain_intent_parser.py` — `_finalize`**

시그니처:
```python
    pending_command: Optional[str] = None,
    user_text: str = "",
) -> VicaIntent:
```
→
```python
    pending_command: Optional[str] = None,
    user_text: str = "",
    pending_deliver: Optional[DestinationData] = None,
) -> VicaIntent:
```

`if draft.intent == "navigate":` 블록이 끝난 뒤(= `if draft.intent in ("cancel", "pause", "resume"):` **앞**)에 추가:

```python
    if draft.intent == "deliver":
        # navigate 와 같은 골격. 확인 문구만 배달용이고, 되묻기·접근불가 처리는 같다.
        matched = match_destination(draft.destination_candidate, list(destinations))
        if matched is None:
            result.intent = "clarify"
            result.reply = result.reply or ASK_DESTINATION
        elif not matched.is_approachable:
            result.matched_destination_id = matched.id
            result.reply = matched.unavailable_reason or matched.confirm_prompt
            result.need_confirm = False
        elif (draft.is_confirmation and pending_deliver is not None
              and matched.id == pending_deliver.id):
            result.matched_destination_id = matched.id
            result.reply = f"{matched.name} 배달을 시작합니다."
            result.need_confirm = False
        else:
            result.matched_destination_id = matched.id
            result.reply = deliver_prompt(matched)
            result.need_confirm = True
```

- [ ] **Step 11: `tts_queue.py` — 확정 deliver 는 침묵**

```python
    if getattr(intent, "intent", "") == "navigate" and not getattr(
        intent, "need_confirm", False
    ):
        return None
```
→
```python
    # deliver 도 같은 규칙 — 출발 멘트("배달을 시작합니다")는 미션이 말한다.
    if (getattr(intent, "intent", "") in ("navigate", "deliver")
            and not getattr(intent, "need_confirm", False)):
        return None
```
docstring 의 `- navigate + need_confirm=False → …` 두 줄 앞에 `(deliver 도 같다)` 를 덧붙인다.

- [ ] **Step 12: 시험 통과 확인**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/test_deliver_intent.py -q 2>&1 | tail -3
```
Expected: `11 passed`.

- [ ] **Step 13: 전체 시험**

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python -m pytest tests/ -q 2>&1 | tail -2
```
Expected: `451 passed` (기준 440 + 11). 빨간 것 0.

- [ ] **Step 14: 실제 LLM 한 번** (네트워크·`.env` 키 필요, 젯슨에서)

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && .venv/bin/python - <<'PY'
from src.langchain_intent_parser import parse_intent
from src.schema import DestinationData
D = [DestinationData(id="office", name="윤지영 교수님 사무실", aliases=["윤지영 교수님"], category2="professor_office"),
     DestinationData(id="wc", name="화장실")]
for t in ["이거 윤지영 교수님한테 가져다줘", "이거 윤지영 교수님 방에 갖다줘", "화장실로 가줘"]:
    r = parse_intent(t, D, history=[])
    print(f"{t!r} -> {r.intent} conf={r.need_confirm} id={r.matched_destination_id} reply={r.reply!r}")
PY
```
Expected: 앞 둘은 `deliver conf=True id=office reply='윤지영 교수님 사무실로 배달할까요?'`, 마지막은 `navigate`. **deliver 가 안 나오면** Step 7(a) 의 예시 문장을 실기 표현으로 보강한다 — 코드가 아니라 프롬프트 문제다.

- [ ] **Step 15: 커밋** (사용자 허락 후)

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && git add src/schema.py src/destination_loader.py src/langchain_intent_parser.py src/tts_queue.py tests/test_deliver_intent.py && git commit -m "feat(intent): 배달(deliver) 의도 — \"OO로 배달할까요?\" 확인과 지름길 확정 (시연용)"
```

---

### Task 3: 미션 — `State.DELIVERING`·배달 출발 멘트·무음 도착·`DeliveryDone`

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py`
- Modify: `vica_ros2_ws/src/vica_interfaces/msg/VicaIntent.msg` (주석만)
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_delivery.py`

**Interfaces:**
- Consumes: `/vica/intent` 의 `intent="deliver"` (Task 2)
- Produces: `State.DELIVERING`, `MSG_DELIVER_START = "{name}{josa} 배달을 시작합니다."`, `DeliveryDone(destination)` 액션
- Produces: `/vica_goal_event` 에 `{"event": "delivery_succeeded", "name": ..., ...}` (Task 5 가 소비)

- [ ] **Step 1: 실패하는 시험 작성** — `vica_ros2_ws/src/vica_mission_manager/test/test_delivery.py`

```python
"""배달(DELIVERING) — 시연 영상용 (2026-09-04).

deliver 의도는 navigate 와 같은 확인 흐름(CONFIRMING → 확정)을 타되,
출발 멘트가 다르고("배달을 시작합니다") 도착은 **무음**이다 — 받을 사람이 그
자리에 없으므로 앱에 DeliveryDone 으로만 알린다. 도착 후 대화도 열지 않는다.
"""
from vica_mission_manager.mission_logic import (
    CancelNav, DeliveryDone, Destination, IntentData, MapBounds, MissionLogic,
    Navigate, NavStatus, Pose2D, Say, State,
    MSG_BUSY, MSG_DELIVER_START, MSG_START, say_destination,
)

BOUNDS = MapBounds(min_x=-50, min_y=-50, max_x=50, max_y=50)
OFFICE = Destination(
    id="office", name="윤지영 교수님 사무실",
    pose=Pose2D(x=3, y=2, yaw_deg=90, frame_id="map"), calibrated=True,
    arrival_message="윤지영 교수님 사무실 앞에 도착했습니다.",
    category="professor_office",
)


def _intent(kind="deliver", confirm=False, dest_id="office"):
    return IntentData(intent=kind, matched_destination_id=dest_id,
                      need_confirm=confirm, safety_flag="normal")


def _say(actions):
    return [a.text for a in actions if isinstance(a, Say)]


def test_confirmed_deliver_starts_with_delivery_ment():
    logic = MissionLogic(arrival_dialog=True)
    acts = logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    assert logic.state == State.DELIVERING
    assert any(isinstance(a, Navigate) for a in acts)
    assert _say(acts) == ["윤지영 교수님 사무실로 배달을 시작합니다."]
    assert say_destination(MSG_START, OFFICE.name) not in _say(acts)


def test_confirm_flow_keeps_deliver_kind():
    """제안(need_confirm) → "그래"(on_confirm_answer) 를 거쳐도 배달로 출발한다."""
    logic = MissionLogic(arrival_dialog=True)
    assert logic.on_intent(_intent(confirm=True), OFFICE, BOUNDS, True, 0.0) == []
    assert logic.state == State.CONFIRMING
    acts = logic.on_confirm_answer(True, OFFICE, BOUNDS, True, 1.0)
    assert logic.state == State.DELIVERING
    assert _say(acts) == [say_destination(MSG_DELIVER_START, OFFICE.name)]


def test_confirm_deny_cancels_delivery_request():
    logic = MissionLogic()
    logic.on_intent(_intent(confirm=True), OFFICE, BOUNDS, True, 0.0)
    logic.on_confirm_answer(False, OFFICE, BOUNDS, True, 1.0)
    assert logic.state == State.IDLE


def test_arrival_is_silent_and_notifies_app():
    logic = MissionLogic(arrival_dialog=True)
    logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    acts = logic.on_tick(1.0, NavStatus.SUCCEEDED)
    assert _say(acts) == []                       # 도착 멘트·질문 없음
    done = [a for a in acts if isinstance(a, DeliveryDone)]
    assert len(done) == 1 and done[0].destination.id == "office"
    assert logic.state == State.ARRIVED
    logic.on_tick(10.0, NavStatus.NONE)           # dwell 뒤 IDLE — 도착 후 대화 없음
    assert logic.state == State.IDLE


def test_navigate_arrival_still_speaks():
    """회귀 방지: 안내 도착 멘트·질문은 그대로다."""
    logic = MissionLogic(arrival_dialog=True)
    logic.on_intent(_intent(kind="navigate"), OFFICE, BOUNDS, True, 0.0)
    acts = logic.on_tick(1.0, NavStatus.SUCCEEDED)
    assert any("도착했습니다" in t for t in _say(acts))
    assert not any(isinstance(a, DeliveryDone) for a in acts)


def test_new_request_during_delivery_is_busy():
    logic = MissionLogic()
    logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    acts = logic.on_intent(_intent(kind="navigate"), OFFICE, BOUNDS, True, 1.0)
    assert _say(acts) == [MSG_BUSY]
    assert logic.state == State.DELIVERING


def test_app_cancel_during_delivery_cancels_goal():
    logic = MissionLogic()
    logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    acts, _ = logic.on_app_cancel(1.0)
    assert any(isinstance(a, CancelNav) for a in acts)
    assert logic.state == State.IDLE


def test_emergency_during_delivery_cancels_goal():
    logic = MissionLogic()
    logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    acts = logic.on_emergency("멈춰", 1.0)
    assert any(isinstance(a, CancelNav) for a in acts)
    assert logic.state == State.ESTOPPED


def test_retry_after_failure_stays_delivering():
    logic = MissionLogic(nav_retry_limit=1, nav_retry_delay_sec=1.0)
    logic.on_intent(_intent(), OFFICE, BOUNDS, True, 0.0)
    logic.on_tick(1.0, NavStatus.FAILED)
    assert logic.state == State.FAILED
    acts = logic.on_tick(3.0, NavStatus.NONE)
    assert logic.state == State.DELIVERING
    assert any(isinstance(a, Navigate) for a in acts)
```

- [ ] **Step 2: 실패 확인**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/test_delivery.py -q 2>&1 | tail -3
```
Expected: `ImportError: cannot import name 'DeliveryDone'`.

- [ ] **Step 3: `mission_logic.py` — 상태**

`class State` 의 `NAVIGATING = "navigating"` **다음 줄**에:
```python
    # 배달 주행 (2026-09-02, 시연 영상용). NAVIGATING 과 같은 주행이지만 사용자가
    # 따라오지 않는다 — 도착을 말하지 않고 앱에만 알린다(DeliveryDone).
    DELIVERING = "delivering"
```

- [ ] **Step 4: `mission_logic.py` — 액션**

`class SetNavSpeedLimit` 정의 **바로 아래**, `Action = Union[...]` **위**에:
```python
@dataclass(frozen=True)
class DeliveryDone:
    """배달 목적지 도착 통보. 노드가 /vica_goal_event 에 `delivery_succeeded` 로 낸다.

    배달은 도착을 **말하지 않는다** — 받을 사람이 그 자리에 없다. 대신 앱이 이
    사건 하나로 관리자에게 알림을 띄운다 (2026-09-02 사용자 결정). 앱은 미션
    상태를 모른다 — 이 사건만 안다.
    """

    destination: Destination
```

- [ ] **Step 5: `mission_logic.py` — 멘트**

`MSG_START = "{name}{josa} 안내를 시작합니다."` **다음 줄**에:
```python
MSG_DELIVER_START = "{name}{josa} 배달을 시작합니다."   # 2026-09-02 사용자 확정
```

- [ ] **Step 6: `mission_logic.py` — 상태 묶음·게이트**

```python
_GOAL_ACTIVE_STATES = (
    State.NAVIGATING, State.APPROACHING, State.TURNING, State.RETURNING
)
```
→
```python
_GOAL_ACTIVE_STATES = (
    State.NAVIGATING, State.DELIVERING, State.APPROACHING, State.TURNING,
    State.RETURNING
)
```

`check_gate` 의
```python
    if intent.intent != "navigate":
        return GateReason.NOT_NAVIGATE
```
→
```python
    if intent.intent not in ("navigate", "deliver"):
        return GateReason.NOT_NAVIGATE
```

`check_cancel_gate` 의
```python
    if state not in (State.NAVIGATING, State.PAUSED, State.WAITING):
```
→
```python
    if state not in (State.NAVIGATING, State.DELIVERING, State.PAUSED, State.WAITING):
```

- [ ] **Step 7: `mission_logic.py` — `__init__` 필드 둘**

`self._confirming_dest_id: Optional[str] = None` **다음 줄**에:
```python
        # 확인 중인 요청의 종류(navigate / deliver). 확인 답("그래")이 왔을 때
        # 같은 종류로 출발해야 배달이 안내로 둔갑하지 않는다.
        self._confirming_kind: str = "navigate"
        # 주행 실패 재시도가 되살릴 상태(NAVIGATING / DELIVERING).
        self._retry_state: State = State.NAVIGATING
```

- [ ] **Step 8: `mission_logic.py` — `on_intent`**

(a) 첫 줄
```python
        if intent.intent != "navigate":
```
→
```python
        if intent.intent not in ("navigate", "deliver"):
```

(b)
```python
        if self.state == State.NAVIGATING:
            # v1 정책: 주행 중 새 목적지는 거부 (소프트 취소는 v2, TODOS.md #4)
            return [Say(MSG_BUSY, priority="response")]
```
→
```python
        if self.state in (State.NAVIGATING, State.DELIVERING):
            # v1 정책: 주행 중 새 목적지는 거부 (소프트 취소는 v2, TODOS.md #4)
            return [Say(MSG_BUSY, priority="response")]
```

(c) 확인 대기 시작 블록
```python
                self.state = State.CONFIRMING
                self._confirming_dest_id = intent.matched_destination_id or None
                self._confirm_deadline = now + self.confirm_timeout_sec
                return []
```
→
```python
                self.state = State.CONFIRMING
                self._confirming_dest_id = intent.matched_destination_id or None
                self._confirming_kind = intent.intent
                self._confirm_deadline = now + self.confirm_timeout_sec
                return []
```

(d) 출발 블록
```python
        assert dest is not None  # check_gate 가 보장
        self.state = State.NAVIGATING
        self.active_destination = dest
        self._confirming_dest_id = None
        self._confirm_deadline = None
        self._announced_milestones = set()
        self._distance_baseline = None
        self._approach.reset()
        return [
            SetNavSpeedLimit(NO_SPEED_LIMIT),
            Say(say_destination(MSG_START, dest.name)),
            Navigate(dest),
        ]
```
→
```python
        assert dest is not None  # check_gate 가 보장
        delivering = intent.intent == "deliver"
        self.state = State.DELIVERING if delivering else State.NAVIGATING
        self.active_destination = dest
        self._confirming_dest_id = None
        self._confirming_kind = "navigate"
        self._confirm_deadline = None
        self._announced_milestones = set()
        self._distance_baseline = None
        self._approach.reset()
        return [
            SetNavSpeedLimit(NO_SPEED_LIMIT),
            Say(say_destination(
                MSG_DELIVER_START if delivering else MSG_START, dest.name)),
            Navigate(dest),
        ]
```

- [ ] **Step 9: `mission_logic.py` — `on_confirm_answer`**

```python
        confirmed = IntentData(
            intent="navigate",
            matched_destination_id=dest.id,
```
→
```python
        confirmed = IntentData(
            intent=self._confirming_kind,
            matched_destination_id=dest.id,
```

- [ ] **Step 10: `mission_logic.py` — `_force_clear_all`**

```python
        if (self.state in (State.NAVIGATING, State.APPROACHING, State.RETURNING)
                and self.active_destination is not None):
```
→
```python
        if (self.state in (State.NAVIGATING, State.DELIVERING,
                           State.APPROACHING, State.RETURNING)
                and self.active_destination is not None):
```

- [ ] **Step 11: `mission_logic.py` — `on_tick` 주행 분기**

(a) 분기 머리
```python
        elif self.state == State.NAVIGATING:
            # 취소 재확인에 답이 없으면 주행을 그대로 이어간다(취소하지 않는다).
```
→
```python
        elif self.state in (State.NAVIGATING, State.DELIVERING):
            # 취소 재확인에 답이 없으면 주행을 그대로 이어간다(취소하지 않는다).
```

(b) 도착 처리
```python
            if nav_status == NavStatus.SUCCEEDED:
                dest = self.active_destination
                text = (
                    dest.arrival_message
                    if dest and dest.arrival_message
                    else MSG_ARRIVED_FALLBACK.format(name=dest.name if dest else "목적지")
                )
                self._approach.reset()
                actions.append(SetNavSpeedLimit(NO_SPEED_LIMIT))
                if self.arrival_dialog and not self._nav_from_app:
```
→
```python
            if nav_status == NavStatus.SUCCEEDED:
                dest = self.active_destination
                text = (
                    dest.arrival_message
                    if dest and dest.arrival_message
                    else MSG_ARRIVED_FALLBACK.format(name=dest.name if dest else "목적지")
                )
                self._approach.reset()
                actions.append(SetNavSpeedLimit(NO_SPEED_LIMIT))
                if self.state == State.DELIVERING:
                    # 배달 도착은 무음 — 받을 사람이 없다. 앱에만 알리고 평소
                    # dwell → IDLE. 도착 후 대화도 열지 않는다.
                    self.state = State.ARRIVED
                    self._dwell_until = now + self.dwell_sec
                    if dest is not None:
                        actions.append(DeliveryDone(dest))
                elif self.arrival_dialog and not self._nav_from_app:
```

(c) 실패 처리 — 재시도가 종류를 기억하게
```python
                failed_dest = self.active_destination
                self.state = State.FAILED
```
→
```python
                failed_dest = self.active_destination
                self._retry_state = self.state     # 재시도 때 같은 종류로
                self.state = State.FAILED
```
그리고 ARRIVED/FAILED 분기의 재시도 실행
```python
                    self._retry_destination = None
                    self.state = State.NAVIGATING
                    self.active_destination = dest
```
→
```python
                    self._retry_destination = None
                    self.state = self._retry_state
                    self.active_destination = dest
```

- [ ] **Step 12: `mission_logic.py` — 정리 함수**

`_to_idle` 의 `self._confirm_deadline = None` **다음 줄**에:
```python
        self._confirming_kind = "navigate"
        self._retry_state = State.NAVIGATING
```
`_enter_estopped` 의 `self._confirm_deadline = None` **다음 줄**에:
```python
        self._confirming_kind = "navigate"
```

- [ ] **Step 13: 로직 시험 통과**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/test_delivery.py -q 2>&1 | tail -3
```
Expected: `9 passed`.

- [ ] **Step 14: `mission_manager_node.py` — import·실행·상태·라우팅**

(a) `from .mission_logic import (` 목록의 `CancelNav,` 아래에 `DeliveryDone,` 추가.

(b) `_run_actions` 의
```python
            elif isinstance(action, SetNavSpeedLimit):
                self._publish_nav_speed_limit(action.percent)
```
**다음**에:
```python
            elif isinstance(action, DeliveryDone):
                # 배달 도착 — 말 대신 앱 알림. 기존 goal_succeeded 와 별개 사건이라
                # 앱이 이것만 팝업으로 띄운다.
                self._publish_goal_event("delivery_succeeded", action.destination)
                self.get_logger().info(
                    f"배달 도착(무음) → 앱 알림: {action.destination.name}")
```

(c) `_publish_robot_state`
```python
        msg.is_moving = self.logic.state == State.NAVIGATING
```
→
```python
        msg.is_moving = self.logic.state in (State.NAVIGATING, State.DELIVERING)
```
(주행 중 YOLO 추론 차단(inference_gate)이 이 값을 본다 — 배달 중에도 꺼진다.)

(d) `_on_intent` 두 곳
```python
        if (self.logic.state == State.RETURNING
                and msg.intent in ("wait", "navigate")):
```
→
```python
        if (self.logic.state == State.RETURNING
                and msg.intent in ("wait", "navigate", "deliver")):
```
```python
            if msg.intent == "navigate" and msg.need_confirm:
                self.logic.exit_arrival_dialog()
```
→
```python
            if msg.intent in ("navigate", "deliver") and msg.need_confirm:
                self.logic.exit_arrival_dialog()
```

- [ ] **Step 15: `VicaIntent.msg` 주석** — `# + wait / finish — …` 절 **다음**에 (필드 선언 `string intent` 위):
```
# + deliver — 배달 (2026-09-02, 시연 영상용). navigate 와 같은 2단계(제안→확정)이며
#   destination_candidate / matched_destination_id 를 같은 뜻으로 채운다.
#   Mission 은 DELIVERING 으로 달리고 도착을 말하지 않는다 — /vica_goal_event 에
#   delivery_succeeded 를 내며 앱이 그것으로 관리자에게 알린다.
```

- [ ] **Step 16: 전체 시험**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q 2>&1 | tail -2
```
Expected: `350 passed, 1 skipped` (기준 341 + 9). 빨간 것 0. (`test_spoken_text` 가 `MSG_DELIVER_START` 를 자동 검사한다 — 긴급어 없음.)

- [ ] **Step 17: 노드 import 스모크** (rclpy 로드까지)

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && source install/setup.bash && python3 -c "import vica_mission_manager.mission_manager_node as n; print('import ok', n.DeliveryDone)"
```
Expected: `import ok <class ...DeliveryDone>` — **주의**: 이 시점엔 install 이 옛 복사본이라 `n.DeliveryDone` 이 없다고 나올 수 있다. 그러면 Step 18 뒤에 다시 돌린다.

- [ ] **Step 18: colcon 빌드** (symlink 설치가 아니므로 필수)

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && colcon build --packages-select vica_mission_manager 2>&1 | tail -3 && source install/setup.bash && python3 -c "import vica_mission_manager.mission_logic as m; print(m.State.DELIVERING, m.MSG_DELIVER_START)"
```
Expected: `Summary: 1 package finished` · `State.DELIVERING {name}{josa} 배달을 시작합니다.`

- [ ] **Step 19: 커밋** (사용자 허락 후)

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && git add src/vica_mission_manager/vica_mission_manager/mission_logic.py src/vica_mission_manager/vica_mission_manager/mission_manager_node.py src/vica_mission_manager/test/test_delivery.py src/vica_interfaces/msg/VicaIntent.msg && git commit -m "feat(mission): 배달(DELIVERING) — 배달 출발 멘트·무음 도착·앱 알림 delivery_succeeded (시연용)"
```

---

### Task 4: 화장실 대기 수락 멘트 — 좌우 안내

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_arrival_dialog.py:80-83`

**Interfaces:**
- Produces: `MSG_WAIT_RESTROOM = "네, 다녀오세요. 남자 화장실은 왼쪽, 여자 화장실은 오른쪽입니다."` — restroom 유형 도착 후 "그래"(시간 없는 대기 수락)에서만.

- [ ] **Step 1: 기존 시험 기대값 수정 + 신규 2건** — `test_arrival_dialog.py`

import 목록의 `MSG_WAIT_DEFAULT,` 옆에 `MSG_WAIT_RESTROOM,` 추가. 그리고
```python
    def test_restroom_affirm_waits_30_no_time_question(self):
        """restroom 은 '네'면 시간 안 묻고 최대 30분 대기."""
        logic = arrive("restroom")
        acts = logic.on_arrival_answer(_intent("affirm"), 3.0)
        assert logic.state == State.WAITING
        assert MSG_WAIT_DEFAULT in _say(acts)
```
→
```python
    def test_restroom_affirm_waits_30_no_time_question(self):
        """restroom 은 '네'면 시간 안 묻고 최대 30분 대기 — 멘트는 좌우 안내
        (2026-09-02 시연용 사용자 확정). 촬영 장소에 맞춰 좌우를 고친다."""
        logic = arrive("restroom")
        acts = logic.on_arrival_answer(_intent("affirm"), 3.0)
        assert logic.state == State.WAITING
        assert _say(acts) == [MSG_WAIT_RESTROOM]
        assert MSG_WAIT_DEFAULT not in _say(acts)

    def test_entrance_deny_keeps_default_wait_ment(self):
        """종료형(entrance) '아니오' = 대기. 화장실이 아니니 좌우 안내는 안 나온다."""
        logic = arrive("entrance")
        acts = logic.on_arrival_answer(_intent("deny"), 3.0)
        assert logic.state == State.WAITING
        assert _say(acts) == [MSG_WAIT_DEFAULT]

    def test_restroom_wait_with_time_keeps_minutes_ment(self):
        """시간을 말했으면 화장실이라도 '20분 대기' 멘트 — 좌우 안내는 시간 없는
        수락에만 붙는다(사용자 대사표 5번 자리)."""
        logic = arrive("restroom")
        acts = logic.on_arrival_answer(_intent("wait", wait_minutes=20), 3.0)
        assert any("20분" in t for t in _say(acts))
        assert MSG_WAIT_RESTROOM not in _say(acts)
```

- [ ] **Step 2: 실패 확인**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/test_arrival_dialog.py -q 2>&1 | tail -3
```
Expected: `ImportError: cannot import name 'MSG_WAIT_RESTROOM'`.

- [ ] **Step 3: `mission_logic.py` — 멘트 상수**

`MSG_WAIT_DEFAULT = ...` 줄 **다음**에:
```python
# 화장실 도착 후 "그래"(시간 없는 대기 수락) 전용 — 시연용 사용자 확정
# (2026-09-02). 좌우는 촬영 장소 실물 기준으로 고친다. 이 멘트에는 "돌아오시면
# 비카야" 안내가 없다 — 사용자 대사표 그대로다.
MSG_WAIT_RESTROOM = "네, 다녀오세요. 남자 화장실은 왼쪽, 여자 화장실은 오른쪽입니다."
```

- [ ] **Step 4: `mission_logic.py` — 도착 유형 기억**

`__init__` 의 `self._asking_time_after_yes = False  # 대기 수락 시 시간을 물을 유형인가` **다음 줄**에:
```python
        self._arrival_category: str = ""   # 방금 도착한 목적지 유형 (대기 멘트 선택용)
```

`_ask_arrival` 의 `self._asking_time_after_yes = ask_time` **다음 줄**에:
```python
        self._arrival_category = category
```

`_reset_arrival_dialog` 의 `self._asking_time_after_yes = False` **다음 줄**에:
```python
        self._arrival_category = ""
```

- [ ] **Step 5: `mission_logic.py` — `_enter_waiting`**

```python
        msg = (MSG_WAIT_DEFAULT if default_msg
               else MSG_WAIT_CONFIRM.format(minutes=minutes))
```
→
```python
        if default_msg and self._arrival_category == "restroom":
            msg = MSG_WAIT_RESTROOM
        elif default_msg:
            msg = MSG_WAIT_DEFAULT
        else:
            msg = MSG_WAIT_CONFIRM.format(minutes=minutes)
```

- [ ] **Step 6: 시험 통과 + 전체**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/test_arrival_dialog.py -q 2>&1 | tail -2 && python3 -m pytest test/ -q 2>&1 | tail -2
```
Expected: 전체 `352 passed, 1 skipped` (350 + 2). 빨간 것 0.

- [ ] **Step 7: colcon 재빌드**

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && colcon build --packages-select vica_mission_manager 2>&1 | tail -2
```
Expected: `Summary: 1 package finished`.

- [ ] **Step 8: 커밋** (사용자 허락 후)

```bash
cd /home/ji_w/VICA-smarthandle/vica_ros2_ws && git add src/vica_mission_manager/vica_mission_manager/mission_logic.py src/vica_mission_manager/test/test_arrival_dialog.py && git commit -m "feat(mission): 화장실 대기 수락 멘트에 좌우 안내 (시연용, MSG_WAIT_RESTROOM)"
```

---

### Task 5: 앱 — `delivery_succeeded` 팝업 1회

**Files:**
- Modify: `VICA_Supervisor/lib/models/goal_event.dart`
- Modify: `VICA_Supervisor/lib/providers/supervisor_provider.dart:966-990`
- Modify: `VICA_Supervisor/test/models/goal_event_test.dart`

**Interfaces:**
- Consumes: `/vica_goal_event` 의 `{"event": "delivery_succeeded", "name": "...", ...}` (Task 3)
- Produces: `GoalEventKind.deliverySucceeded` — `needsPopup=true`, `isFailure=false`, title `배달 완료`.

- [ ] **Step 1: 실패하는 시험** — `test/models/goal_event_test.dart` 의 `group('무엇을 알리는가', () {` 안, `'성공은 팝업을 띄우지 않는다'` 시험 **다음**에:

```dart
    test('배달 완료는 팝업을 띄운다 — 받을 사람이 그 자리에 없다', () {
      // 안내 도착은 로봇이 말로 알리지만, 배달은 말할 상대가 없어 앱이 알린다
      // (2026-09-02 사용자 결정). 성공 팝업 금지 원칙의 유일한 예외다.
      final e = event('delivery_succeeded', name: '윤지영 교수님 사무실');
      expect(e.kind, GoalEventKind.deliverySucceeded);
      expect(e.needsPopup, isTrue);
      expect(e.isFailure, isFalse);
      expect(e.title, '배달 완료');
      expect(e.description, contains('윤지영 교수님 사무실'));
    });
```

- [ ] **Step 2: 실패 확인**

```bash
cd /home/ji_w/VICA-smarthandle/VICA_Supervisor && flutter test test/models/goal_event_test.dart 2>&1 | tail -5
```
Expected: 컴파일 오류 `Member not found: 'deliverySucceeded'`.

- [ ] **Step 3: `goal_event.dart` — enum·판정·문구**

(a) enum 의 `succeeded('goal_succeeded'),` **다음**에:
```dart
  /// 배달 도착 (2026-09-02, 시연용). 로봇은 도착을 말하지 않는다 — 받을 사람이
  /// 그 자리에 없다. 그래서 이 사건만은 성공이어도 팝업을 띄운다.
  deliverySucceeded('delivery_succeeded'),
```

(b) `needsPopup`
```dart
  bool get needsPopup =>
      this == GoalEventKind.failed ||
```
→
```dart
  bool get needsPopup =>
      this == GoalEventKind.deliverySucceeded ||
      this == GoalEventKind.failed ||
```

(c) `title` switch 의 `case GoalEventKind.failed:` **앞**에:
```dart
      case GoalEventKind.deliverySucceeded:
        return '배달 완료';
```

(d) `description` switch 의 `case GoalEventKind.failed:` **앞**에:
```dart
      case GoalEventKind.deliverySucceeded:
        return '${where}에 물건이 도착했습니다. 수령을 확인해 주세요.$detail';
```

- [ ] **Step 4: `supervisor_provider.dart` — 주행 끝 처리에 포함**

`_handleGoalEvent` 의 switch 에서
```dart
      case GoalEventKind.succeeded:
      case GoalEventKind.failed:
```
→
```dart
      case GoalEventKind.succeeded:
      case GoalEventKind.deliverySucceeded:
      case GoalEventKind.failed:
```

- [ ] **Step 5: 시험·분석**

```bash
cd /home/ji_w/VICA-smarthandle/VICA_Supervisor && flutter test test/models/goal_event_test.dart 2>&1 | tail -3 && flutter analyze 2>&1 | tail -3
```
Expected: `All tests passed!` · `No issues found!`

- [ ] **Step 6: 리눅스 빌드**

```bash
cd /home/ji_w/VICA-smarthandle/VICA_Supervisor && flutter build linux --release 2>&1 | tail -3 && ls -la build/linux/arm64/release/bundle/vica_supervisor
```
Expected: `Built build/linux/arm64/release/bundle/vica_supervisor` 와 오늘 날짜의 파일.

- [ ] **Step 7: 커밋** (사용자 허락 후)

```bash
cd /home/ji_w/VICA-smarthandle/VICA_Supervisor && git add lib/models/goal_event.dart lib/providers/supervisor_provider.dart test/models/goal_event_test.dart && git commit -m "feat(app): 배달 완료(delivery_succeeded) 팝업 — 성공 팝업 금지의 유일한 예외 (시연용)"
```

---

### Task 6: 재기동·종단 확인 (실기, 코드 없음)

**전제:** 새 지도 매핑·목적지 등록이 끝난 상태. 목적지에 **"윤지영 교수님 사무실"** (별칭 `윤지영 교수님`, 유형 `교수연구실`) 과 **화장실** (유형 `화장실`) 이 있어야 한다.

- [ ] **Step 1: 음성 `.env` 에 목적지 경로** — 새 지도 id 를 `<MAP>` 에

```bash
cd /home/ji_w/VICA-smarthandle/vica-voice-llm && grep -q VICA_DESTINATIONS_YAML .env || printf '\n# 시연 지도 목적지 (웨이크워드 STT 귀띔·TTS 워밍업이 이 경로를 읽는다)\nVICA_DESTINATIONS_YAML=%s\n' "$HOME/vica_data/destinations/<MAP>/destinations.yaml" >> .env; grep VICA_DESTINATIONS_YAML .env
```

- [ ] **Step 2: 확인 멘트 조사 손질** — 앱이 저장한 `"…으로 안내해드릴까요?"` 를 고친다 (파일: `~/vica_data/destinations/<MAP>/destinations.yaml`). `화장실으로` → `화장실로`, `윤지영 교수님 사무실으로` → `윤지영 교수님 사무실로`. 그 뒤 미션 재시작(또는 `ros2 service type /vica/mission/reload_destinations` 로 타입을 확인해 호출).

- [ ] **Step 3: 재기동 순서** — 미션 노드(`colcon build` 반영) → 음성 launch(`map_id:=<MAP>`) → 앱 새 빌드 실행(`DISPLAY=:0 ./build/linux/arm64/release/bundle/vica_supervisor`).

- [ ] **Step 4: 종단 확인 — 배달** (바퀴 띄우고 또는 통제된 공간에서)

| 말 | 기대 | 확인 |
| --- | --- | --- |
| "비카야" | "네?" | |
| "이거 윤지영 교수님한테 가져다줘" | "윤지영 교수님 사무실로 배달할까요?" · 미션 로그 `intent=deliver … confirm=True -> state=confirming` | |
| "그래" | "윤지영 교수님 사무실로 배달을 시작합니다." · 로그 `state=delivering` · 앱 `is_moving` | |
| 도착 | **아무 말 없음** · 미션 로그 `배달 도착(무음) → 앱 알림` · 앱 팝업 **"배달 완료"** | |
| 3초 뒤 | 로그 `state=idle` | |

- [ ] **Step 5: 종단 확인 — 안내 회귀** — "화장실로 가줘" → "화장실로 안내해드릴까요?" → "그래" → "화장실로 안내를 시작합니다." → 도착 "화장실 앞에 도착했습니다. 다녀오시는 동안 여기서 기다릴까요?" → "그래" → **"네, 다녀오세요. 남자 화장실은 왼쪽, 여자 화장실은 오른쪽입니다."** (좌우가 현장과 다르면 `MSG_WAIT_RESTROOM` 만 고치고 Task 4 Step 7 재빌드).

- [ ] **Step 6: 배달 중 앱 취소 1회** — 앱 취소 버튼 → 로봇이 서고 로그 `state=idle`. (`_force_clear_all` 에 DELIVERING 을 넣은 이유 — 촬영 중 NG 낼 때 쓴다.)

---

## 자체 검토

**Spec 커버리지 (§0 + 사용자 결정 5항):**
- B-2 "배달할까요?" → Task 2 `_finalize`/`deliver_prompt` ✅
- B-3 "배달을 시작합니다" → Task 3 `MSG_DELIVER_START` + `_confirming_kind` ✅
- B-4 무음 + 앱 알림 1회 → Task 3 `DeliveryDone`/`delivery_succeeded`, Task 5 팝업 ✅
- 유형 교수연구실·대기 대화 없음 → Task 3 도착 분기가 `_ask_arrival` 을 타지 않음 ✅
- 앱은 상태를 모른다 → `RobotState.msg` 미변경, 이벤트 하나만 ✅
- A-5 좌우 안내 (화장실 도착 시에만) → Task 4 ✅
- 영상용 브랜치 → Task 1 ✅
- `VicaIntent` 계약 → Task 2 Literal + Task 3 주석 ✅

**타입·이름 일관성:** `deliver_prompt`(loader) ↔ `_pending_deliver_destination`(parser) 글자 일치가 계약 — 둘 다 같은 함수로 만든다. `DeliveryDone.destination: Destination` ↔ 노드 `_publish_goal_event(event, destination)`. `delivery_succeeded` 문자열 = 노드·dart enum wire 동일. `_confirming_kind: str` ↔ `IntentData.intent: str`. `_retry_state: State`.

**빠뜨리기 쉬운 곳(확인함):** `_GOAL_ACTIVE_STATES`(긴급어·E-stop 취소), `_force_clear_all`(앱 취소), `check_cancel_gate`(음성 취소), `is_moving`(YOLO 게이트), 재시도의 상태 복원, `_enter_estopped` 의 `_confirming_kind` 초기화, `tts_queue` 침묵 규칙, `exit_arrival_dialog` 라우팅.

**손대지 않은 것(의도적):** `check_pause_gate`(배달 중 일시정지는 거부 — "지금은 안내 중이 아닙니다"), `on_arrival_answer` 의 `navigate` 분기(도착 대화 중 배달 요청은 `need_confirm=True` 로 대화를 닫고 일반 경로로 간다), 앱 저장 화면의 "으로" 하드코딩([[app-hardcodes-destination-ments]] — Task 6 Step 2 로 손질).
