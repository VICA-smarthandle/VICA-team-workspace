# 미션 요청 반응 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로봇이 사용자의 어떤 음성 요청에도 꼭 한마디 하고(규칙 1), LLM 은 로봇이 할 일을 혼자 약속하지 않으며(규칙 2), 대답이 없거나 이상하면 질문마다 한 번 다시 묻게 한다 — 결정 5개 포함.

**Architecture:** 미션의 음성 요청 갈래를 노드에서 `MissionLogic.on_voice_intent` 한곳으로 옮기고(동작 그대로), 그 위에 반응표 230칸을 순수 시험으로 못 박는다. 새 반응은 `_react_by_table`의 상태별 처리기에 더하고, 처리기가 맡지 않는 칸은 옛 갈래가 그대로 처리한다. 음성은 지시문(규칙 2)과 순수 함수 모듈 `mission_question.py`(미션이 질문 중이면 LLM 대답을 지운다)를 고친다. 공용 메시지·토픽·노드는 그대로다.

**Tech Stack:** Python 3.10 · ROS 2 Humble · pytest 6.2(미션, 시스템 python3) · pytest(음성, 저장소 `.venv`) · CosyVoice3(굽기, 사용자)

**Spec:** `docs/superpowers/specs/2026-10-08-mission-request-reactions-design.md` (정본 페이지 https://claude.ai/artifact/ShUUYxV6JU648gTteKGZ3n v3)

## 이 계획을 만든 방법

계획의 코드는 모두 임시 복사본에서 먼저 짜고 시험한 것이다. 작업마다 "시험만 넣었을 때"와 "구현까지 넣었을 때"의
결과를 실제로 재서 각 Step 의 Expected 에 적었다. 작업 1~17과 선택 18의 패치 전부(시험·구현 36개)를
**지금 두 저장소의 코드 복사본에 처음부터 끝까지 적용**해 깔끔하게 들어가는 것과 최종 시험 결과(미션 983 통과, 음성 772 통과 + 굽기 전
`TestBaked` 1개)를 확인했다. ROS 를 켠 상태의 노드 불러오기와 노드 시험(`test_nav_cancel_race.py`)도 확인했다.
저장소 코드는 이 계획을 쓰는 동안 바꾸지 않았다.

## 요약 — 작업 순서

| 작업 | 저장소 | 내용 | 바뀌는 칸 |
| --- | --- | --- | --- |
| 1 | 미션 | 음성 요청 판단을 로직 한곳으로(동작 그대로) | 0 |
| 2 | 미션 | 반응표 230칸 시험(바꿀 56칸은 대기) | 0 |
| 3 | 미션 | 잠깐 | 8 |
| 4 | 미션 | 기다려 | 8 |
| 5 | 미션 | 다 됐어 | 5 |
| 6 | 미션 | 다시 가자 | 8 |
| 7 | 미션 | 아니요·취소, 취소 확인의 네·아니요 | 6 |
| 8 | 미션 | 결정 3: 대기 중 취소 | 2 |
| 9 | 미션 | 결정 1: 홈 가는 중 기다려 → 직전 목적지 대기 장소 | 10 |
| 10 | 미션 | 결정 2·4: 시간 질문의 네, 확인 질문 중 다른 목적지 | 3 |
| 11 | 미션 | 접근 질문에 목적지로 답하기 | 3 |
| 12 | 미션 | 다시 묻기(질문마다 한 번) | 1 |
| 13 | 음성 | 지시문: 약속 금지·접근 질문 목적지·기다리지 마·부정 질문·질문 중 못 알아들음 | — |
| 14 | 음성 | 미션이 질문 중이면 LLM 대답 지우기 | — |
| 15 | 음성 | "네, XX로…" 확인 질문 인식, 취소 확인의 아니요 → 미션 | — |
| 16 | 음성 | 음성이 쥔 "다시 출발할까요?" 다시 묻기 | — |
| 17 | 음성 | 새 문장 목록·굽기(사용자) | — |
| 18 | 둘 다 | (선택, 승인 시) 접근 질문 다시 묻기 | — |
| 19 | 실기 | 사용자 판정 | — |

**짝으로 들어가야 하는 것.** 미션과 음성은 함께 배포한다. 작업 12(미션이 다시 묻기)는 작업 14(LLM 침묵)와, 작업 7(취소
확인의 아니요를 미션이 받기)은 작업 15(음성이 아니요를 deny 로 넘기기)와, 작업 11(접근 질문 목적지 답)은 작업 13·14와
짝이다. 한쪽만 들어가면 두 목소리가 나거나 "아니요" 뒤에 미션이 "취소할까요?"를 또 묻는다. 그래서 실기(작업 19)는 1~17을
모두 넣은 뒤에 한다.

## Global Constraints

- **코드는 사용자가 이 계획을 승인하고 실행 방식을 고른 뒤에만 바꾼다**(10-07 사용자 지시). 커밋은 작업마다 하고, **push 는 하지 않는다**(사용자 요청 시에만).
- **새 브랜치를 만들지 않는다**(10-02 지침) — 두 저장소 모두 지금의 `after_feedback_waiting` 위에서 한다. 다른 이름이 필요하면 먼저 묻는다.
- 시작 조건: 다른 세션의 미커밋 변경이 먼저 커밋돼 있어야 한다 — 확인됨(ROS `d6a9f06` 홈 알림, 음성 `a18a7a0` "비카야" 오감지 대책). 시작할 때 `git status`로 이 계획이 고칠 파일(아래 File Structure)에 남의 변경이 없는지 다시 본다. 있으면 멈추고 묻는다 — 섞어 커밋하지 않는다.
- 새 노드 없음, 공용 메시지(`vica_interfaces`)·토픽·서비스 변경 없음. Safety·E-stop·Nav2 경로와 "미션이 Goal 권한자" 원칙은 그대로다.
- 새 문장은 사용자가 정한 둘뿐이다: "안내가 필요 없으신가요?", "네, {확인 질문}"(목적지마다). '입구 앞' M2·M2′ 6문장은 기존 틀(`MSG_WAIT_SPOT_CONFIRM`·`MSG_WAIT_SPOT_DEFAULT`)에 기존 장소 말(`WAIT_PLACE_AT_DESTINATION`)을 넣은 것이다. "안내를 받으시겠어요?"는 작업 18(승인 시)에서만.
- 미션 문장과 음성 사본(`mission_phrases.py`)은 글자가 같아야 한다 — `test_mission_phrases.py`가 대조한다.
- 굽기(CosyVoice)는 **로봇 스택을 모두 내린 상태에서만**(RAM 약 3 GB). `assets/`는 gitignore 라 `git add -f`.
- 커밋 메시지는 저장소 기존 문체(`type(scope): 평서형 설명 — 근거`). 끝에 아래 두 줄을 붙인다 — 한 번 정해 두고 쓴다:

```bash
export VICA_TRAILER=$'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_019d3r5Lo3xoGRrEm7mcZ2QE'
```

- 모든 명령은 작업공간 루트(`~/VICA-smarthandle`)에서 시작한다. 패치는 `git -C <저장소> apply "$PWD/docs/…"`로 넣는다. **패치가 안 들어가면(`error: patch failed`) 억지로 고치지 말고 멈추고 보고한다** — 그 사이 누가 같은 곳을 바꾼 것이다.

## Review Focus

설계가 말하지 않았지만 사람이 실제로 부딪힐 입력 다섯 가지와, 그것을 못 박은 시험:

1. **질문 중 옆사람 말이 두 번 이상 섞일 때** — 다시 묻기는 질문마다 한 번이고 그 뒤는 흘려보내야 한다. 작업 12 `test_confirm_strange_answer_reasks_once`, `test_cancel_question_strange_answer_reasks_once`.
2. **틱이 늦게 와서 다시 묻기 시각과 마감이 한 틱에 겹칠 때** — 묻자마자 접으면 안 된다. 작업 12 `test_late_tick_still_reasks_before_folding`.
3. **손 놓기 기다림에서 시간을 바꿨는데 옛 대기 안내의 재생 끝이 늦게 올 때** — 새 안내가 끝날 때까지 떠나면 안 된다. 작업 4 `test_release_waits_for_the_new_wait_sentence`.
4. **확인 질문 중 갈 수 없는 곳으로 바꾸려 할 때** — 이유를 말하고 묻던 질문은 남아야 한다. 작업 10 `test_switch_to_a_closed_place_keeps_the_question`.
5. **홈에 도착한 뒤의 "기다려"** — 직전 목적지를 잊어 그냥 쉬는 중의 말이 돼야 한다(옛 대기 장소로 가면 안 된다). 작업 9 `test_after_home_wait_is_plain_idle_again`.

## File Structure

| 파일 | 책임 | 작업 |
| --- | --- | --- |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py` | 음성 요청 반응의 모든 판단(`on_voice_intent`·처리기·다시 묻기 시계) | 1, 3~12, 18 수정 |
| `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py` | 요청을 로직에 넘기고 실행·기록만 | 1, 18 수정 |
| `vica_ros2_ws/src/vica_mission_manager/test/reaction_states.py` | 시험용 상태 만들기(공개 함수만) | 2 신규 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py` | 반응표 230칸 | 2 신규, 3~12 `PENDING` 줄이기 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py` | 칸 뒤에 이어지는 일 | 4 신규, 5~12·18 이어 쓰기 |
| `vica_ros2_ws/src/vica_mission_manager/test/test_{arrival_dialog,destination_change,mission_logic,wait_spot}.py` | 옛 동작을 못 박은 시험 10개 | 10·12 고침 |
| `vica-voice-llm/src/langchain_intent_parser.py` | 지시문(규칙 2), 확인 질문 인식, 취소 확인 아니요 | 13·15 수정 |
| `vica-voice-llm/src/local_rules.py` | 로컬 규칙 1번(접근 질문) | 13 수정 |
| `vica-voice-llm/src/mission_question.py` | 미션이 질문 중인지·LLM 대답 지우기·다시 출발 다시 묻기(순수 함수) | 14 신규, 16 수정 |
| `vica-voice-llm/src/ros_node.py` | 위 판단을 발행 직전에 적용, `/vica/listen_state` 구독 | 14·16 수정 |
| `vica-voice-llm/src/mission_phrases.py` | 미션 새 문장의 사본·굽기/미리 합성 목록 | 14·15·17·18 수정 |
| `vica-voice-llm/tests/test_mission_reactions_voice.py` | 음성 쪽 반응표 시험 | 13 신규, 14~16 이어 쓰기 |
| `vica-voice-llm/tests/test_{command_intents,mission_phrases}.py` | 취소 확인 아니요·문장 계약 | 15·17·18 수정 |

`mission_logic.py`는 이미 4,000줄이 넘지만 **쪼개지 않는다.** 이 계획은 처리기 몇 개와 시계 셋을 더할 뿐이고, 상태기계를 가르는 일은 이 작업의 범위를 넘는다.

## 시험 실행 명령과 지금 기준

```bash
# 미션 (순수 로직, ROS 필요 없음) — 지금: 3 failed, 719 passed, 1 skipped
(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)

# 음성 — 지금: 전부 통과
(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)
```

시험 명령은 괄호(하위 셸)로 돌려 작업공간 루트를 벗어나지 않는다 — 패치 명령의 `$PWD`가 루트여야 한다.

- 미션의 원래 실패 3개(`test_progress_narration.py`의 `test_speed_limit_never_goes_back_up`·`test_resume_resets_the_ladder`·`test_stage_list_is_configurable`)는 이 계획과 무관하다 — 모든 Expected 에 그대로 남는다.
- 워크스페이스를 source 한 셸에서 그냥 `pytest`를 쓰면 `install/`의 옛 사본을 시험한다. 위처럼 `python3 -m pytest`(현재 폴더가 먼저)로 돌린다.
- `test_nav_cancel_race.py`는 rclpy 가 있어야 돈다(ROS source 뒤). 거기엔 원래 실패 2개(`TestIdleCancelSync`)가 있다.

---

### Task 1: 음성 요청의 판단을 미션 로직 한곳으로 옮긴다 (동작 그대로)

노드 `_on_intent`와 도우미 넷(`_on_voice_mission_command`·`_on_confirm_answer`·`_on_voice_answer`·
`_on_arrival_answer`)이 하던 갈래를 `MissionLogic.on_voice_intent`로 옮긴다. 노드는 요청을 로직에 넘기고
나온 동작을 실행·기록만 한다(10-07 호출 반응표 `on_wake_call`과 같은 방식). 동작은 한 칸도 바꾸지 않는다 —
이 작업의 시험은 기존 시험 722개가 그대로 통과하는 것이다. 다음 작업의 반응표 시험이 이 함수를 부른다.

노드 기록 줄이 하나로 바뀐다: `음성 요청 intent=… dest=… confirm=…: 상태 -> 상태 말=[…]`(말이 없으면
`(말 없음)`). 옛 줄 "도착 후 답 intent=…", "affirm/deny 무시", "음성 … 처리/거부"를 grep 하는 분석 도구가
있으면 이 줄로 바꾼다.

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py`

**Interfaces:**
- Produces: `MissionLogic.on_voice_intent(intent: IntentData, now: float, lookup: Callable[[str], Optional[Destination]], bounds: Optional[MapBounds] = None, nav_ready: bool = True) -> list`
- Produces: `MissionLogic._react_by_table(intent, now, lookup, bounds, nav_ready) -> Optional[list]` — 이 작업에서는 늘 `None`(옛 갈래로). 작업 3부터 칸을 채운다.
- Produces: `MissionLogic._route_voice_intent(...) -> list`(옛 노드 갈래 그대로), `MissionLogic._voice_mission_command(kind: str, now: float, nav_ready: bool) -> list`
- Produces: 노드 `_lookup_destination(dest_id: str) -> Optional[Destination]`

- [ ] **Step 1: 기준 시험 — 옮기기 전 결과를 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 719 passed, 1 skipped` (실패 3개는 `test_progress_narration.py`의 원래 실패 — 이 작업과 무관)

- [ ] **Step 2: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/01-code.patch"
```

<details><summary>01-code.patch (305줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index e865627..831c3d4 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -14,7 +14,7 @@ import math
 
 from dataclasses import dataclass, replace
 from enum import Enum
-from typing import Optional, Sequence, Union
+from typing import Callable, Optional, Sequence, Union
 
 from .approach_speed import ApproachSpeedLadder, NO_SPEED_LIMIT
 from .grip_meter import GripMeter
@@ -1451,6 +1451,97 @@ class MissionLogic:
 
     # -- 입력 이벤트 -----------------------------------------------------------
 
+    # -- 음성 요청 반응 (미션 요청 반응표, 2026-10-08) -------------------------
+    def on_voice_intent(
+        self,
+        intent: IntentData,
+        now: float,
+        lookup: Callable[[str], Optional[Destination]],
+        bounds: Optional[MapBounds] = None,
+        nav_ready: bool = True,
+    ) -> list:
+        """음성 요청 하나에 대한 반응. 노드는 나온 동작을 실행하고 기록만 한다.
+
+        갈래(라우팅)는 2026-10-08 노드 _on_intent 에서 이리로 옮겼다 — 반응표(상태 18 ×
+        요청 11)를 ROS 없이 순수 시험으로 전수 확인하려고. 호출 반응표(on_wake_call)와
+        같은 방식이다. lookup 은 목적지 id → Destination(없으면 None)이다.
+        설계: docs/superpowers/specs/2026-10-08-mission-request-reactions-design.md
+        """
+        reacted = self._react_by_table(intent, now, lookup, bounds, nav_ready)
+        if reacted is not None:
+            return reacted
+        return self._route_voice_intent(intent, now, lookup, bounds, nav_ready)
+
+    def _react_by_table(
+        self,
+        intent: IntentData,
+        now: float,
+        lookup: Callable[[str], Optional[Destination]],
+        bounds: Optional[MapBounds],
+        nav_ready: bool,
+    ) -> Optional[list]:
+        """반응표로 새로 정한 칸(2026-10-08). 맡지 않는 칸은 None — 옛 갈래가 처리한다."""
+        return None
+
+    def _route_voice_intent(
+        self,
+        intent: IntentData,
+        now: float,
+        lookup: Callable[[str], Optional[Destination]],
+        bounds: Optional[MapBounds],
+        nav_ready: bool,
+    ) -> list:
+        """옛 노드 _on_intent 의 갈래 그대로(2026-10-08 이전 동작)."""
+        kind = intent.intent
+        actions: list = []
+        # 복귀 주행 중 늦게 도착한 답 — 마지막 그물 (2026-08-30 실기: 무응답 오판으로
+        # 떠난 직후 도착한 답이 버려져 세울 방법이 없었다). 복귀를 조용히 멈추고
+        # (ASKING_NEXT) 아래 갈래가 그 뜻을 그대로 처리한다 — wait 는 대기, navigate
+        # 제안은 확인 흐름.
+        if self.state == State.RETURNING and kind in ("wait", "navigate"):
+            actions.extend(self.on_return_brake(now, quiet=True))
+        # 도착 후 대화 중이면 답을 on_arrival_answer 로 보낸다 — 같은 말이라도 이
+        # 상태에선 뜻이 다르다(도착 후 cancel = 홈 복귀 등). 예외: 새 목적지 '제안'은
+        # 대화를 닫고 아래 일반 확인 흐름(CONFIRMING)으로 합류한다(2026-08-30 실기).
+        if self.is_awaiting_arrival_answer():
+            if kind == "navigate" and intent.need_confirm:
+                self.exit_arrival_dialog()
+            else:
+                next_dest = (lookup(intent.matched_destination_id)
+                             if kind == "navigate" else None)
+                return actions + self.on_arrival_answer(
+                    intent, now, next_dest=next_dest, bounds=bounds, nav_ready=nav_ready)
+        if kind in ("cancel", "pause", "resume"):
+            return actions + self._voice_mission_command(kind, now, nav_ready)
+        # 짧은 답(affirm/deny)은 어느 질문의 답인지 상태가 정한다. CONFIRMING 이면 확인
+        # 질문의 답 — 목적지는 미션이 이미 안다(2026-08-31). 그 외에는 접근 질문 배선 —
+        # AWAITING_USER 가 아니면 on_approach_answer 가 빈 목록을 돌려준다.
+        if kind in ("affirm", "deny"):
+            if self.state == State.CONFIRMING:
+                dest = lookup(self.confirming_dest_id or "")
+                return actions + self.on_confirm_answer(
+                    kind == "affirm", dest, bounds, nav_ready, now)
+            return actions + self.on_approach_answer(kind == "affirm", now)
+        dest = lookup(intent.matched_destination_id)
+        return actions + self.on_intent(intent, dest, bounds, nav_ready, now)
+
+    def _voice_mission_command(self, kind: str, now: float, nav_ready: bool) -> list:
+        """음성 취소·일시정지·재개(옛 노드 _on_voice_mission_command). 취소는 곧바로 하지
+        않고 "취소할까요?"로 되묻는다 — 이미 되물은 상태의 두 번째 "취소"는 긍정이다.
+        관문에 걸리면 이유를 말한다."""
+        if kind == "cancel":
+            if self.cancel_confirm_pending:
+                return self.on_cancel_confirm_answer(True, now)
+            actions, reason = self.on_cancel_confirm_request(now)
+        elif kind == "pause":
+            actions, reason = self.on_pause_request(now)
+        else:
+            actions, reason = self.on_resume_request(nav_ready, now)
+        if reason != GateReason.OK:
+            msg = _REJECT_MESSAGES.get(reason)
+            return [Say(msg, priority="response")] if msg else []
+        return actions
+
     def on_intent(
         self,
         intent: IntentData,
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py b/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
index 32c964e..c408ff0 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
@@ -97,7 +97,6 @@ from .mission_logic import (
     SpinInPlace,
     Pose2D,
     State,
-    _REJECT_MESSAGES,
     check_gate,
     doa_to_spin_yaw,
     nav_behavior_tree,
@@ -662,47 +661,7 @@ class MissionManagerNode(Node):
             return None
 
     def _on_intent(self, msg: VicaIntent) -> None:
-        # 복귀 주행 중 늦게 도착한 답 — 마지막 그물 (2026-08-30 실기: 무응답
-        # 오판으로 떠난 직후 도착한 답이 버려져 세울 방법이 없었다). 복귀를
-        # 조용히 멈추고(ASKING_NEXT) 아래 라우팅이 그 뜻을 그대로 처리한다
-        # — wait 는 대기, navigate 제안은 확인 흐름. finish 는 이미 홈으로
-        # 가는 중이라 제외(그대로 간다).
-        if (self.logic.state == State.RETURNING
-                and msg.intent in ("wait", "navigate")):
-            self._run_actions(self.logic.on_return_brake(self._now(), quiet=True))
-            self.get_logger().info(f"복귀 중 답 도착({msg.intent}) — 복귀 취소")
-
-        # 도착 후 대화 중이면 답(wait/finish/cancel/affirm/deny)을
-        # on_arrival_answer 로 보낸다 — 같은 말이라도 이 상태에선 뜻이 다르다
-        # (도착 후 cancel = 홈 복귀 등). 상태 판정은 로직이 갖고 있다.
-        # 예외: 새 목적지 '제안'(navigate + need_confirm)은 대화의 답이 아니라
-        # 새 안내 요청이다 — 대화를 닫고 아래 일반 확인 흐름(CONFIRMING)으로
-        # 합류시킨다. 제안에서 바로 출발하면 확인 질문 전에 달리고, 뒤따라온
-        # 확정 답이 MSG_BUSY 로 거절된다 (2026-08-30 실기).
-        if self.logic.is_awaiting_arrival_answer():
-            if msg.intent == "navigate" and msg.need_confirm:
-                self.logic.exit_arrival_dialog()
-                # return 하지 않는다 — 아래 일반 경로가 이어서 처리한다.
-            else:
-                self._on_arrival_answer(msg)
-                return
-        # 음성 취소·일시정지·재개는 service 와 같은 로직을 탄다.
-        # 다만 취소는 바로 실행하지 않고 되물어 확인한 뒤에만 처리한다.
-        if msg.intent in ("cancel", "pause", "resume"):
-            self._on_voice_mission_command(msg)
-            return
-        # 짧은 답(affirm/deny)은 어느 질문의 답인지 여기의 상태가 정한다.
-        # CONFIRMING 이면 확인 질문("…로 안내해 드릴까요?")의 답 — 목적지는
-        # 미션이 이미 알고 있어 LLM 의 추측 없이 직접 확정한다(2026-08-31).
-        # 그 외에는 접근 질문 배선 — AWAITING_USER 가 아니면
-        # on_approach_answer 가 빈 목록을 돌려주고, 그때는 무시가 정답이다.
-        if msg.intent in ("affirm", "deny"):
-            if self.logic.state == State.CONFIRMING:
-                self._on_confirm_answer(msg.intent == "affirm")
-            else:
-                self._on_voice_answer(msg.intent == "affirm")
-            return
-
+        """음성 요청. 판단은 로직(on_voice_intent)이 하고 여기선 실행·기록만 한다(2026-10-08)."""
         intent = IntentData(
             intent=msg.intent,
             matched_destination_id=msg.matched_destination_id,
@@ -710,15 +669,21 @@ class MissionManagerNode(Node):
             safety_flag=msg.safety_flag,
             wait_minutes=int(getattr(msg, "wait_minutes", -1)),
         )
-        dest = self.destinations.get(msg.matched_destination_id) or None
-        actions = self.logic.on_intent(
-            intent, dest, self.map_bounds, self._nav2_ready(), self._now()
-        )
-        self.get_logger().info(
-            f"intent={msg.intent} dest={msg.matched_destination_id or '-'} "
-            f"confirm={msg.need_confirm} -> state={self.logic.state.value}"
-        )
+        before = self.logic.state
+        actions = self.logic.on_voice_intent(
+            intent, self._now(), self._lookup_destination,
+            bounds=self.map_bounds, nav_ready=self._nav2_ready())
         self._run_actions(actions)
+        said = [a.text for a in actions if isinstance(a, Say)]
+        self.get_logger().info(
+            f"음성 요청 intent={msg.intent} dest={msg.matched_destination_id or '-'} "
+            f"confirm={msg.need_confirm}: {before.value} -> {self.logic.state.value}"
+            + (f" 말={said}" if said else " (말 없음)"))
+
+    def _lookup_destination(self, dest_id: str) -> Optional[Destination]:
+        if not dest_id:
+            return None
+        return self.destinations.get(dest_id) or None
 
     def _on_tts_done(self, msg: String) -> None:
         """TTS 가 끊기지 않고 끝까지 재생한 문장. 접근 질문일 때만 시계를 켠다.
@@ -741,56 +706,6 @@ class MissionManagerNode(Node):
         # 로직이 자기 M2 문장과 대조하므로 다른 문장이면 무시된다.
         self._run_actions(self.logic.on_wait_speech_spoken(msg.data, self._now()))
 
-    def _on_confirm_answer(self, affirmative: bool) -> None:
-        """확인 질문의 네/아니오. 확인 중 목적지를 되찾아 로직에 넘긴다."""
-        dest_id = self.logic.confirming_dest_id or ""
-        dest = self.destinations.get(dest_id) or None
-        before = self.logic.state
-        actions = self.logic.on_confirm_answer(
-            affirmative, dest, self.map_bounds, self._nav2_ready(), self._now()
-        )
-        self.get_logger().info(
-            f"확인 응답 {'긍정' if affirmative else '부정'}: dest={dest_id or '-'} "
-            f"{before.value} -> {self.logic.state.value}"
-        )
-        self._run_actions(actions)
-
-    def _on_voice_answer(self, affirmative: bool) -> None:
-        before = self.logic.state
-        actions = self.logic.on_approach_answer(affirmative, self._now())
-        if not actions:
-            self.get_logger().info(
-                f"affirm/deny 무시: state={before.value} (접근 질문 대기 중이 아님)"
-            )
-            return
-        self._run_actions(actions)
-        self.get_logger().info(
-            f"접근 응답 {'긍정' if affirmative else '부정'}: "
-            f"{before.value} -> {self.logic.state.value}"
-        )
-
-    def _on_arrival_answer(self, msg: VicaIntent) -> None:
-        """도착 후 대화 중의 답. navigate 답이면 다음 목적지를 넘기고, 로직이 평소
-        목적지 요청과 같은 관문을 거친 뒤 NAVIGATING 으로 간다(2026-10-07 수리 — 예전엔
-        관문 없이 넘겨 비공개·위치 미등록·주행 미준비 목적지로도 출발했다)."""
-        intent = IntentData(
-            intent=msg.intent,
-            matched_destination_id=msg.matched_destination_id,
-            need_confirm=msg.need_confirm,
-            safety_flag=msg.safety_flag,
-            wait_minutes=int(getattr(msg, "wait_minutes", -1)),
-        )
-        next_dest = None
-        if msg.intent == "navigate":
-            next_dest = self.destinations.get(msg.matched_destination_id) or None
-        before = self.logic.state
-        actions = self.logic.on_arrival_answer(
-            intent, self._now(), next_dest=next_dest,
-            bounds=self.map_bounds, nav_ready=self._nav2_ready())
-        self._run_actions(actions)
-        self.get_logger().info(
-            f"도착 후 답 intent={msg.intent}: {before.value} -> {self.logic.state.value}")
-
     def _on_wake(self, msg: String) -> None:
         """/vica/wake — 호출 반응표대로 대답할지 정한다(2026-10-07, 판단은 로직).
 
@@ -899,45 +814,6 @@ class MissionManagerNode(Node):
             f"{before.value} -> {self.logic.state.value}"
         )
 
-    def _on_voice_mission_command(self, msg: VicaIntent) -> None:
-        """음성으로 온 취소·일시정지·재개를 처리한다.
-
-        취소는 잘못 알아들으면 안내가 끊기므로 곧바로 실행하지 않는다.
-        "취소할까요?"로 되묻고, 확인 응답이 와야 실제로 취소한다. 확인을 기다리는
-        동안에도 주행은 계속되며, 응답이 없으면 그대로 안내를 이어간다.
-        """
-        now = self._now()
-        before = self.logic.state
-
-        if msg.intent == "cancel":
-            if self.logic.cancel_confirm_pending:
-                # 이미 되물은 상태에서 다시 "취소"라고 하면 긍정으로 본다.
-                actions = self.logic.on_cancel_confirm_answer(True, now)
-                self._run_actions(actions)
-                self.get_logger().info(
-                    f"음성 취소 확정: {before.value} -> {self.logic.state.value}"
-                )
-                return
-            actions, reason = self.logic.on_cancel_confirm_request(now)
-        elif msg.intent == "pause":
-            actions, reason = self.logic.on_pause_request(now)
-        else:
-            actions, reason = self.logic.on_resume_request(self._nav2_ready(), now)
-
-        if reason != GateReason.OK:
-            message = _REJECT_MESSAGES.get(reason)
-            if message:
-                self._run_actions([Say(message, priority="response")])
-            self.get_logger().warn(
-                f"음성 {msg.intent} 거부: state={before.value} reason={reason.value}"
-            )
-            return
-
-        self._run_actions(actions)
-        self.get_logger().info(
-            f"음성 {msg.intent} 처리: {before.value} -> {self.logic.state.value}"
-        )
-
     # -- 취소 / 일시정지 / 재개 service -------------------------------------------
     #
     # 앱·CLI 는 요청만 보내고 허용 여부는 여기서 판정한다. 음성(LLM)은 같은 로직을
```

</details>

- [ ] **Step 3: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 719 passed, 1 skipped` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 4: 노드가 ROS 환경에서 불러와지고 노드 시험이 그대로인지 본다**

```bash
(source /opt/ros/humble/setup.bash && source vica_ros2_ws/install/setup.bash
 cd vica_ros2_ws/src/vica_mission_manager
 PYTHONPATH=$PWD:$PYTHONPATH python3 -c "import vica_mission_manager.mission_manager_node; print('ok')"
 PYTHONPATH=$PWD:$PYTHONPATH python3 -m pytest test/test_nav_cancel_race.py -q -p no:cacheprovider)
```
Expected: `ok`, 그리고 `2 failed, 21 passed` — 실패 2개(`TestIdleCancelSync`)는 원래 실패다(옮기기 전에도 같다).

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/vica_mission_manager/mission_logic.py src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
git -C vica_ros2_ws commit -m "refactor(mission): 음성 요청 갈래를 로직(on_voice_intent)으로 옮긴다 — 반응표 전수 시험 준비, 동작 그대로" -m "$VICA_TRAILER"
```


### Task 2: 반응표 시험 — 230칸을 못 박고, 바꿀 56칸은 작업마다 푼다

상태 22갈래(반응표 18상태 + 쪽지에 적힌 경우: 홈 가다 세운 뒤 두 가지, 주행 중 바꾸기 질문, 대기 중
"어디로 모실까요?" 뒤, 답이 없어 떠난 뒤 복귀) × 음성 요청 10종 = 230칸. "비카야" 열은
`test_wake_reaction.py`가 이미 맡는다. 상태는 기존 시험과 같은 공개 함수로 만든다(필드를 직접 고치지 않는다).

기대값은 바뀐 뒤(설계 4절) 기준이다. 아직 구현 전인 56칸은 `PENDING`에 작업 번호와 함께 두고
`xfail(strict=True)`로 돈다 — 작업마다 자기 칸을 `PENDING`에서 지우면 그 칸이 보통 시험이 된다. 안 바뀌는
174칸은 지금 동작을 그대로 못 박는다(작업 1의 옮기기가 동작을 안 바꿨다는 확인이기도 하다).

**Files:**
- Create: `vica_ros2_ws/src/vica_mission_manager/test/reaction_states.py`
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`

**Interfaces:**
- Consumes: `on_voice_intent` (작업 1)
- Produces: `test/reaction_states.py` — `ROWS: dict[str, Callable[[], tuple[MissionLogic, float]]]`, `REQUESTS: dict[str, IntentData]`, `lookup`, `BOUNDS`, `intent(kind, **kw)`, 상태 만들기 함수들(`idle`, `navigating`, `asking`, `returning`, `returning_late`, `idle_braked`, `confirming`, `confirming_change`, `paused`, `waiting_release`, `waiting`, `waiting_asked`, `awaiting_user`, `turning` …), 목적지 `ROOM`·`TOILET`·`SPOT_DEST`·`ELEV`
- Produces: `test/test_reaction_table.py` — `EXPECT`, `PENDING`(작업 번호 → 칸)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/02-test.patch"
```

<details><summary>02-test.patch (704줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/reaction_states.py b/src/vica_mission_manager/test/reaction_states.py
new file mode 100644
index 0000000..a639e2a
--- /dev/null
+++ b/src/vica_mission_manager/test/reaction_states.py
@@ -0,0 +1,259 @@
+"""미션 요청 반응표(2026-10-08) 시험용 상태 만들기 — 실제 흐름과 같은 공개 함수만 쓴다.
+
+상태마다 새 MissionLogic 을 그 상태로 데려가고 (logic, 다음 시각)을 돌려준다. 필드를 직접
+고치지 않는다 — 실제 흐름이 채우는 내부 값(질문 종류·대기 장소·복귀 사다리 등)이 그대로
+남아야 칸의 동작이 실기와 같다. 정본 설계: docs/superpowers/specs/2026-10-08-mission-request-
+reactions-design.md
+"""
+from vica_mission_manager.mission_logic import (
+    ApproachRequest,
+    Destination,
+    IntentData,
+    MapBounds,
+    MissionLogic,
+    NavStatus,
+    Pose2D,
+    WaitSpot,
+)
+
+BOUNDS = MapBounds(min_x=-50, min_y=-50, max_x=50, max_y=50)
+HOME = Destination(id="__home__", name="홈", pose=Pose2D(0, 0, 0, "map"))
+SPOT = WaitSpot(x=1.97, y=-1.42, yaw_deg=0.0, side="right")
+APPROACH = ApproachRequest(goal=Pose2D(1.0, 0.5, 30.0, "map"), track_id=7)
+
+
+def dest(category="", **kw) -> Destination:
+    d = dict(id="d1", name="화장실", pose=Pose2D(3, 2, 90, "map"), calibrated=True,
+             arrival_message="화장실 앞에 도착했습니다.", category=category)
+    d.update(kw)
+    return Destination(**d)
+
+
+ROOM = dest(id="r409", name="409호", pose=Pose2D(5, 1, 0, "map"), arrival_message="")
+TOILET = dest("restroom", id="wc", pose=Pose2D(-3, 2, 90, "map"))
+SPOT_DEST = dest("restroom", id="d1", wait_spot=SPOT, door_yaw_deg=270.0, name="화장실 입구",
+                 pose=Pose2D(3.21, -1.05, 90.0, "map"),
+                 arrival_message="화장실 입구 앞에 도착했습니다.")
+ELEV = dest(id="elev", name="엘리베이터", pose=Pose2D(6, -2, 0, "map"), arrival_message="")
+ALL = {d.id: d for d in (ROOM, TOILET, SPOT_DEST, ELEV)}
+
+
+def lookup(dest_id: str):
+    return ALL.get(dest_id) if dest_id else None
+
+
+def intent(kind="navigate", **kw) -> IntentData:
+    d = dict(intent=kind, matched_destination_id="", need_confirm=False, safety_flag="normal")
+    d.update(kw)
+    return IntentData(**d)
+
+
+def go(d: Destination) -> IntentData:
+    return intent(matched_destination_id=d.id)
+
+
+def new_logic(**kw) -> MissionLogic:
+    kw.setdefault("return_destination", HOME)
+    kw.setdefault("arrival_dialog", True)
+    return MissionLogic(**kw)
+
+
+# ---- 상태 ------------------------------------------------------------------
+def idle():
+    return new_logic(), 1.0
+
+
+def navigating(d=ROOM, t=0.0):
+    logic = new_logic()
+    logic.on_intent(go(d), d, BOUNDS, True, t)
+    return logic, t + 1.0
+
+
+def asking(d=TOILET):
+    """도착 질문. TOILET(restroom)은 대기형 "다녀오시는 동안 여기서 기다릴까요?"."""
+    logic = new_logic()
+    logic.on_intent(go(d), d, BOUNDS, True, 0.0)
+    logic.on_tick(1.0, NavStatus.SUCCEEDED)
+    logic.on_arrival_question_spoken(2.0)
+    return logic, 3.0
+
+
+def returning(d=TOILET):
+    """도착 질문에 "다 됐어" → 홈 복귀 중(안내를 마친 뒤)."""
+    logic, t = asking(d)
+    logic.on_arrival_answer(intent("finish"), t)
+    return logic, t + 1.0
+
+
+def returning_late():
+    """도착 질문에 끝내 답이 없어 떠난 직후 — 늦은 답이 올 수 있는 복귀."""
+    logic, _ = asking()
+    logic.on_tick(10.5, NavStatus.NONE)          # 8초 침묵 → 같은 질문 한 번 더
+    logic.on_arrival_question_spoken(11.0)
+    logic.on_tick(19.5, NavStatus.NONE)          # 또 침묵 → 떠나기 예고(3초 유예)
+    logic.on_tick(23.0, NavStatus.NONE)          # 유예 끝 → 홈으로
+    return logic, 24.0
+
+
+def idle_braked(d=TOILET):
+    """홈 가다 "비카야"로 세운 뒤 — 15초 재개 사다리가 걸린 IDLE. TOILET 은 대기 장소가 없다."""
+    logic, t = returning(d)
+    logic.on_return_brake(t)
+    return logic, t + 1.0
+
+
+def idle_braked_spot():
+    """대기 장소가 있는 목적지(SPOT_DEST)에서 안내를 마치고 홈 가다 세운 뒤."""
+    return idle_braked(SPOT_DEST)
+
+
+def confirming():
+    logic = new_logic()
+    logic.on_intent(intent(matched_destination_id=TOILET.id, need_confirm=True),
+                    TOILET, BOUNDS, True, 0.0)
+    return logic, 1.0
+
+
+def confirming_change():
+    """안내 주행 중 다른 목적지 제안 → 멈추고 바꿀지 묻는 중."""
+    logic, t = navigating(ROOM)
+    logic.on_intent(intent(matched_destination_id=TOILET.id, need_confirm=True),
+                    TOILET, BOUNDS, True, t)
+    return logic, t + 1.0
+
+
+def paused():
+    logic, t = navigating()
+    logic.on_pause_request(t)
+    return logic, t + 1.0
+
+
+def failed():
+    logic = new_logic(nav_retry_limit=0)
+    logic.on_intent(go(ROOM), ROOM, BOUNDS, True, 0.0)
+    logic.on_tick(10.0, NavStatus.FAILED)
+    return logic, 10.5
+
+
+def arrived():
+    """관리자 주행 도착(질문 없음)."""
+    logic = new_logic()
+    logic.on_app_destination(dest("restroom"), BOUNDS, True, 0.0)
+    logic.on_tick(10.0, NavStatus.SUCCEEDED)
+    return logic, 10.5
+
+
+def asking_wait_time():
+    logic, t = asking(dest("reception", id="desk", name="안내데스크"))
+    logic.on_arrival_answer(intent("affirm"), t)
+    logic.on_arrival_question_spoken(t + 1.0)
+    return logic, t + 2.0
+
+
+def waiting_release(minutes=10):
+    logic = new_logic()
+    logic.on_intent(go(SPOT_DEST), SPOT_DEST, BOUNDS, True, 0.0)
+    logic.on_tick(1.0, NavStatus.SUCCEEDED)
+    logic.on_arrival_question_spoken(2.0)
+    logic.on_arrival_answer(intent("wait", wait_minutes=minutes), 3.0)
+    return logic, 4.0
+
+
+def moving_to_wait_spot():
+    logic, _ = waiting_release()
+    logic.on_wait_speech_spoken(logic._release_text, 7.0)
+    logic.on_tick(7.1, NavStatus.NONE)
+    return logic, 7.5
+
+
+def waiting():
+    logic, _ = moving_to_wait_spot()
+    logic.on_tick(8.0, NavStatus.SUCCEEDED)
+    return logic, 9.0
+
+
+def waiting_asked():
+    """대기 중 "다 됐어" → "네, 어디로 모실까요?"를 물은 직후(30초 안)."""
+    logic, t = waiting()
+    logic.on_intent(intent("finish"), None, BOUNDS, True, t)
+    return logic, t + 1.0
+
+
+def moving_back_to_dest():
+    logic, _ = moving_to_wait_spot()
+    logic.on_tick(40.0, NavStatus.FAILED)
+    return logic, 41.0
+
+
+def approaching():
+    logic = new_logic()
+    logic.on_approach_request(APPROACH, BOUNDS, True, 0.0)
+    return logic, 1.0
+
+
+def awaiting_user():
+    logic, _ = approaching()
+    logic.on_tick(5.0, NavStatus.SUCCEEDED)
+    logic.on_approach_question_spoken(6.0)
+    return logic, 7.0
+
+
+def turning():
+    logic, t = awaiting_user()
+    logic.on_approach_answer(True, t)
+    return logic, t + 1.0
+
+
+def seeking():
+    logic = new_logic(wake_doa_sign=1.0)
+    logic.on_wake_doa(90.0, True, 1.0)
+    return logic, 2.0
+
+
+def estopped():
+    logic, t = navigating()
+    logic.on_estop(True, t)
+    return logic, t + 1.0
+
+
+# 반응표의 행. 상태 이름 정본은 State 다 — 같은 상태의 갈래(세운 뒤·바꾸기 질문·늦은 답)는
+# 반응표 칸의 쪽지에 적힌 경우를 따로 세운 것이다.
+ROWS = {
+    "IDLE": idle,
+    "IDLE_BRAKED": idle_braked,
+    "IDLE_BRAKED_SPOT": idle_braked_spot,
+    "CONFIRMING": confirming,
+    "CONFIRMING_CHANGE": confirming_change,
+    "NAVIGATING": navigating,
+    "PAUSED": paused,
+    "FAILED": failed,
+    "ARRIVED": arrived,
+    "ASKING_NEXT": asking,
+    "ASKING_WAIT_TIME": asking_wait_time,
+    "WAITING_RELEASE": waiting_release,
+    "MOVING_TO_WAIT_SPOT": moving_to_wait_spot,
+    "WAITING": waiting,
+    "WAITING_ASKED": waiting_asked,
+    "MOVING_BACK_TO_DEST": moving_back_to_dest,
+    "APPROACHING": approaching,
+    "AWAITING_USER": awaiting_user,
+    "TURNING": turning,
+    "SEEKING": seeking,
+    "RETURNING": returning,
+    "RETURNING_LATE": returning_late,
+    "ESTOPPED": estopped,
+}
+
+# 반응표의 열 — 음성 요청 11종. 목적지 요청은 지금 가는 곳과 다른 엘리베이터로 한다.
+REQUESTS = {
+    "navp": intent(matched_destination_id=ELEV.id, need_confirm=True),
+    "navc": intent(matched_destination_id=ELEV.id),
+    "wait": intent("wait", wait_minutes=-1),
+    "finish": intent("finish"),
+    "cancel": intent("cancel"),
+    "pause": intent("pause"),
+    "resume": intent("resume"),
+    "yes": intent("affirm"),
+    "no": intent("deny"),
+    "talk": intent("question"),
+}
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
new file mode 100644
index 0000000..56bf793
--- /dev/null
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -0,0 +1,433 @@
+"""미션 요청 반응표 전수 시험 (2026-10-08, 규칙 1·2·결정 5개·다시 묻기).
+
+상태(행) × 음성 요청(열)마다 미션이 하는 말과 바뀐 상태를 못 박는다. 정본 설계:
+docs/superpowers/specs/2026-10-08-mission-request-reactions-design.md, 정본 페이지 v3.
+"비카야" 열은 test_wake_reaction.py 가 맡는다. 질문·잡담(talk)은 LLM 이 답하고 미션은
+말하지 않는다 — 그 칸의 규칙 2는 음성 저장소 시험이 맡는다.
+
+PENDING 의 칸은 아직 구현 전이다(strict xfail). 작업마다 자기 칸을 지운다.
+"""
+import pytest
+
+from reaction_states import BOUNDS, REQUESTS, ROWS, lookup
+from vica_mission_manager.mission_logic import (
+    MSG_APPROACH_ACCEPTED,
+    MSG_APPROACH_BUSY,
+    MSG_APPROACH_DECLINED,
+    MSG_ARRIVAL_RETRY,
+    MSG_ASK_ENTRANCE,
+    MSG_ASK_WAIT_TIME,
+    MSG_CANCEL_CONFIRM,
+    MSG_CONFIRM_PROMPT_FALLBACK,
+    MSG_CONFIRM_TIMEOUT,
+    MSG_ESTOP_REJECT,
+    MSG_FINISH,
+    MSG_NOT_NAVIGATING,
+    MSG_NOT_PAUSED,
+    MSG_PAUSED,
+    MSG_RESUMED,
+    MSG_START,
+    MSG_WAIT_DEFAULT,
+    MSG_WAIT_FINISH_ASK,
+    MSG_WAIT_SPOT_CONFIRM,
+    MSG_WAIT_SPOT_DEFAULT,
+    MSG_WAKE_GREETING,
+    Say,
+    State,
+    say_destination,
+)
+
+START_ELEV = say_destination(MSG_START, "엘리베이터")
+START_TOILET = say_destination(MSG_START, "화장실")
+RESUMED_ROOM = say_destination(MSG_RESUMED, "409호")
+ASK_ELEV = say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "엘리베이터")
+ASK_TOILET = say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "화장실")
+M2P_FRONT = MSG_WAIT_SPOT_DEFAULT.format(place="입구 앞")
+M2P_RIGHT = MSG_WAIT_SPOT_DEFAULT.format(place="입구 오른쪽")
+M2_RIGHT_10 = MSG_WAIT_SPOT_CONFIRM.format(minutes=10, place="입구 오른쪽")
+# 새 문장(설계 7절). 상수는 해당 작업이 만든다 — 여기서는 글자 그대로 못 박는다.
+SWITCH_ELEV = "네, 엘리베이터로 안내해드릴까요?"
+GOING_ROOM = "지금 409호로 가는 중이에요."
+NEED_ASK = "안내가 필요 없으신가요?"
+
+COLS = ("navp", "navc", "wait", "finish", "cancel", "pause", "resume", "yes", "no", "talk")
+
+EXPECT = {
+    "IDLE": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "finish": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "pause": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "resume": ((MSG_NOT_PAUSED,), State.IDLE),
+        "yes": ((), State.IDLE),
+        "no": ((), State.IDLE),
+        "talk": ((), State.IDLE),
+    },
+    "IDLE_BRAKED": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2P_FRONT,), State.MOVING_BACK_TO_DEST),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "pause": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "resume": ((MSG_FINISH,), State.RETURNING),
+        "yes": ((), State.IDLE),
+        "no": ((), State.IDLE),
+        "talk": ((), State.IDLE),
+    },
+    "IDLE_BRAKED_SPOT": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2P_RIGHT,), State.WAITING_RELEASE),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "pause": ((MSG_NOT_NAVIGATING,), State.IDLE),
+        "resume": ((MSG_FINISH,), State.RETURNING),
+        "yes": ((), State.IDLE),
+        "no": ((), State.IDLE),
+        "talk": ((), State.IDLE),
+    },
+    "CONFIRMING": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((SWITCH_ELEV,), State.CONFIRMING),
+        "wait": ((MSG_CONFIRM_TIMEOUT,), State.IDLE),
+        "finish": ((MSG_CONFIRM_TIMEOUT,), State.IDLE),
+        "cancel": ((MSG_CONFIRM_TIMEOUT,), State.IDLE),
+        "pause": ((MSG_WAKE_GREETING,), State.CONFIRMING),
+        "resume": ((ASK_TOILET,), State.CONFIRMING),
+        "yes": ((START_TOILET,), State.NAVIGATING),
+        "no": ((MSG_CONFIRM_TIMEOUT,), State.IDLE),
+        "talk": ((), State.CONFIRMING),
+    },
+    "CONFIRMING_CHANGE": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((SWITCH_ELEV,), State.CONFIRMING),
+        "wait": ((RESUMED_ROOM,), State.NAVIGATING),
+        "finish": ((MSG_CANCEL_CONFIRM,), State.CONFIRMING),
+        "cancel": ((MSG_CANCEL_CONFIRM,), State.CONFIRMING),
+        "pause": ((MSG_PAUSED,), State.PAUSED),
+        "resume": ((RESUMED_ROOM,), State.NAVIGATING),
+        "yes": ((START_TOILET,), State.NAVIGATING),
+        "no": ((RESUMED_ROOM,), State.NAVIGATING),
+        "talk": ((), State.CONFIRMING),
+    },
+    "NAVIGATING": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((ASK_ELEV,), State.CONFIRMING),
+        "wait": ((MSG_PAUSED,), State.PAUSED),
+        "finish": ((MSG_CANCEL_CONFIRM,), State.NAVIGATING),
+        "cancel": ((MSG_CANCEL_CONFIRM,), State.NAVIGATING),
+        "pause": ((MSG_PAUSED,), State.PAUSED),
+        "resume": ((GOING_ROOM,), State.NAVIGATING),
+        "yes": ((), State.NAVIGATING),
+        "no": ((), State.NAVIGATING),
+        "talk": ((), State.NAVIGATING),
+    },
+    "PAUSED": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((MSG_PAUSED,), State.PAUSED),
+        "finish": ((MSG_CANCEL_CONFIRM,), State.PAUSED),
+        "cancel": ((MSG_CANCEL_CONFIRM,), State.PAUSED),
+        "pause": ((MSG_PAUSED,), State.PAUSED),
+        "resume": ((RESUMED_ROOM,), State.NAVIGATING),
+        "yes": ((), State.PAUSED),
+        "no": ((), State.PAUSED),
+        "talk": ((), State.PAUSED),
+    },
+    "FAILED": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((), State.FAILED),
+        "finish": ((), State.FAILED),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.FAILED),
+        "pause": ((MSG_NOT_NAVIGATING,), State.FAILED),
+        "resume": ((MSG_NOT_PAUSED,), State.FAILED),
+        "yes": ((), State.FAILED),
+        "no": ((), State.FAILED),
+        "talk": ((), State.FAILED),
+    },
+    "ARRIVED": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((), State.ARRIVED),
+        "finish": ((), State.ARRIVED),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.ARRIVED),
+        "pause": ((MSG_NOT_NAVIGATING,), State.ARRIVED),
+        "resume": ((MSG_NOT_PAUSED,), State.ARRIVED),
+        "yes": ((), State.ARRIVED),
+        "no": ((), State.ARRIVED),
+        "talk": ((), State.ARRIVED),
+    },
+    "ASKING_NEXT": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((MSG_WAIT_DEFAULT,), State.WAITING),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_FINISH,), State.RETURNING),
+        "pause": ((MSG_WAKE_GREETING,), State.ASKING_NEXT),
+        "resume": ((MSG_WAIT_FINISH_ASK,), State.ASKING_NEXT),
+        "yes": ((MSG_WAIT_DEFAULT,), State.WAITING),
+        "no": ((MSG_ASK_ENTRANCE,), State.ASKING_NEXT),
+        "talk": ((), State.ASKING_NEXT),
+    },
+    "ASKING_WAIT_TIME": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((MSG_ASK_WAIT_TIME,), State.ASKING_WAIT_TIME),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_FINISH,), State.RETURNING),
+        "pause": ((MSG_WAKE_GREETING,), State.ASKING_WAIT_TIME),
+        "resume": ((MSG_WAIT_FINISH_ASK,), State.ASKING_NEXT),
+        "yes": ((MSG_ASK_WAIT_TIME,), State.ASKING_WAIT_TIME),
+        "no": ((MSG_ASK_ENTRANCE,), State.ASKING_NEXT),
+        "talk": ((), State.ASKING_WAIT_TIME),
+    },
+    "WAITING_RELEASE": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2_RIGHT_10,), State.WAITING_RELEASE),
+        "finish": ((MSG_WAIT_FINISH_ASK,), State.WAITING_RELEASE),
+        "cancel": ((MSG_ASK_ENTRANCE,), State.ASKING_NEXT),
+        "pause": ((MSG_WAKE_GREETING,), State.WAITING_RELEASE),
+        "resume": ((MSG_WAIT_FINISH_ASK,), State.WAITING_RELEASE),
+        "yes": ((), State.WAITING_RELEASE),
+        "no": ((MSG_ASK_ENTRANCE,), State.ASKING_NEXT),
+        "talk": ((), State.WAITING_RELEASE),
+    },
+    "MOVING_TO_WAIT_SPOT": {
+        "navp": ((), State.MOVING_TO_WAIT_SPOT),
+        "navc": ((), State.MOVING_TO_WAIT_SPOT),
+        "wait": ((), State.MOVING_TO_WAIT_SPOT),
+        "finish": ((), State.MOVING_TO_WAIT_SPOT),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.MOVING_TO_WAIT_SPOT),
+        "pause": ((MSG_NOT_NAVIGATING,), State.MOVING_TO_WAIT_SPOT),
+        "resume": ((MSG_NOT_PAUSED,), State.MOVING_TO_WAIT_SPOT),
+        "yes": ((), State.MOVING_TO_WAIT_SPOT),
+        "no": ((), State.MOVING_TO_WAIT_SPOT),
+        "talk": ((), State.MOVING_TO_WAIT_SPOT),
+    },
+    "WAITING": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2_RIGHT_10,), State.WAITING),
+        "finish": ((MSG_WAIT_FINISH_ASK,), State.WAITING),
+        "cancel": ((NEED_ASK,), State.WAITING),
+        "pause": ((MSG_NOT_NAVIGATING,), State.WAITING),
+        "resume": ((MSG_WAIT_FINISH_ASK,), State.WAITING),
+        "yes": ((), State.WAITING),
+        "no": ((), State.WAITING),
+        "talk": ((), State.WAITING),
+    },
+    "WAITING_ASKED": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2_RIGHT_10,), State.WAITING),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((NEED_ASK,), State.WAITING),
+        "pause": ((MSG_NOT_NAVIGATING,), State.WAITING),
+        "resume": ((MSG_WAIT_FINISH_ASK,), State.WAITING),
+        "yes": ((MSG_WAIT_FINISH_ASK,), State.WAITING),
+        "no": ((MSG_FINISH,), State.RETURNING),
+        "talk": ((), State.WAITING),
+    },
+    "MOVING_BACK_TO_DEST": {
+        "navp": ((), State.MOVING_BACK_TO_DEST),
+        "navc": ((), State.MOVING_BACK_TO_DEST),
+        "wait": ((), State.MOVING_BACK_TO_DEST),
+        "finish": ((), State.MOVING_BACK_TO_DEST),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.MOVING_BACK_TO_DEST),
+        "pause": ((MSG_NOT_NAVIGATING,), State.MOVING_BACK_TO_DEST),
+        "resume": ((MSG_NOT_PAUSED,), State.MOVING_BACK_TO_DEST),
+        "yes": ((), State.MOVING_BACK_TO_DEST),
+        "no": ((), State.MOVING_BACK_TO_DEST),
+        "talk": ((), State.MOVING_BACK_TO_DEST),
+    },
+    "APPROACHING": {
+        "navp": ((), State.APPROACHING),
+        "navc": ((MSG_APPROACH_BUSY,), State.APPROACHING),
+        "wait": ((), State.APPROACHING),
+        "finish": ((), State.APPROACHING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.APPROACHING),
+        "pause": ((MSG_NOT_NAVIGATING,), State.APPROACHING),
+        "resume": ((MSG_NOT_PAUSED,), State.APPROACHING),
+        "yes": ((), State.APPROACHING),
+        "no": ((), State.APPROACHING),
+        "talk": ((), State.APPROACHING),
+    },
+    "AWAITING_USER": {
+        "navp": ((MSG_APPROACH_ACCEPTED,), State.TURNING),
+        "navc": ((MSG_APPROACH_ACCEPTED,), State.TURNING),
+        "wait": ((), State.AWAITING_USER),
+        "finish": ((), State.AWAITING_USER),
+        "cancel": ((MSG_APPROACH_DECLINED,), State.RETURNING),
+        "pause": ((MSG_WAKE_GREETING,), State.AWAITING_USER),
+        "resume": ((MSG_WAKE_GREETING,), State.AWAITING_USER),
+        "yes": ((MSG_APPROACH_ACCEPTED,), State.TURNING),
+        "no": ((MSG_APPROACH_DECLINED,), State.RETURNING),
+        "talk": ((), State.AWAITING_USER),
+    },
+    "TURNING": {
+        "navp": ((), State.TURNING),
+        "navc": ((), State.TURNING),
+        "wait": ((), State.TURNING),
+        "finish": ((), State.TURNING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.TURNING),
+        "pause": ((MSG_NOT_NAVIGATING,), State.TURNING),
+        "resume": ((MSG_NOT_PAUSED,), State.TURNING),
+        "yes": ((), State.TURNING),
+        "no": ((), State.TURNING),
+        "talk": ((), State.TURNING),
+    },
+    "SEEKING": {
+        "navp": ((), State.SEEKING),
+        "navc": ((MSG_APPROACH_BUSY,), State.SEEKING),
+        "wait": ((), State.SEEKING),
+        "finish": ((), State.SEEKING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.SEEKING),
+        "pause": ((MSG_NOT_NAVIGATING,), State.SEEKING),
+        "resume": ((MSG_NOT_PAUSED,), State.SEEKING),
+        "yes": ((), State.SEEKING),
+        "no": ((), State.SEEKING),
+        "talk": ((), State.SEEKING),
+    },
+    "RETURNING": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2P_FRONT,), State.MOVING_BACK_TO_DEST),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.RETURNING),
+        "pause": ((MSG_WAKE_GREETING,), State.IDLE),
+        "resume": ((MSG_NOT_PAUSED,), State.RETURNING),
+        "yes": ((), State.RETURNING),
+        "no": ((), State.RETURNING),
+        "talk": ((), State.RETURNING),
+    },
+    "RETURNING_LATE": {
+        "navp": ((), State.CONFIRMING),
+        "navc": ((START_ELEV,), State.NAVIGATING),
+        "wait": ((M2P_FRONT,), State.MOVING_BACK_TO_DEST),
+        "finish": ((MSG_FINISH,), State.RETURNING),
+        "cancel": ((MSG_NOT_NAVIGATING,), State.RETURNING),
+        "pause": ((MSG_WAKE_GREETING,), State.IDLE),
+        "resume": ((MSG_NOT_PAUSED,), State.RETURNING),
+        "yes": ((M2P_FRONT,), State.MOVING_BACK_TO_DEST),
+        "no": ((MSG_FINISH,), State.RETURNING),
+        "talk": ((), State.RETURNING),
+    },
+    "ESTOPPED": {
+        "navp": ((MSG_ESTOP_REJECT,), State.ESTOPPED),
+        "navc": ((MSG_ESTOP_REJECT,), State.ESTOPPED),
+        "wait": ((), State.ESTOPPED),
+        "finish": ((), State.ESTOPPED),
+        "cancel": ((MSG_ESTOP_REJECT,), State.ESTOPPED),
+        "pause": ((MSG_ESTOP_REJECT,), State.ESTOPPED),
+        "resume": ((MSG_ESTOP_REJECT,), State.ESTOPPED),
+        "yes": ((), State.ESTOPPED),
+        "no": ((), State.ESTOPPED),
+        "talk": ((), State.ESTOPPED),
+    },
+}
+
+PENDING = {
+    # Task 3
+    "ASKING_NEXT.pause": 3,
+    "ASKING_WAIT_TIME.pause": 3,
+    "AWAITING_USER.pause": 3,
+    "CONFIRMING.pause": 3,
+    "PAUSED.pause": 3,
+    "RETURNING.pause": 3,
+    "RETURNING_LATE.pause": 3,
+    "WAITING_RELEASE.pause": 3,
+    # Task 4
+    "CONFIRMING.wait": 4,
+    "CONFIRMING_CHANGE.wait": 4,
+    "IDLE.wait": 4,
+    "NAVIGATING.wait": 4,
+    "PAUSED.wait": 4,
+    "WAITING.wait": 4,
+    "WAITING_ASKED.wait": 4,
+    "WAITING_RELEASE.wait": 4,
+    # Task 5
+    "CONFIRMING.finish": 5,
+    "CONFIRMING_CHANGE.finish": 5,
+    "IDLE.finish": 5,
+    "NAVIGATING.finish": 5,
+    "PAUSED.finish": 5,
+    # Task 6
+    "ASKING_NEXT.resume": 6,
+    "ASKING_WAIT_TIME.resume": 6,
+    "AWAITING_USER.resume": 6,
+    "CONFIRMING.resume": 6,
+    "NAVIGATING.resume": 6,
+    "WAITING.resume": 6,
+    "WAITING_ASKED.resume": 6,
+    "WAITING_RELEASE.resume": 6,
+    # Task 7
+    "ASKING_WAIT_TIME.no": 7,
+    "AWAITING_USER.cancel": 7,
+    "CONFIRMING.cancel": 7,
+    "WAITING_ASKED.no": 7,
+    "WAITING_RELEASE.cancel": 7,
+    "WAITING_RELEASE.no": 7,
+    # Task 8
+    "WAITING.cancel": 8,
+    "WAITING_ASKED.cancel": 8,
+    # Task 9
+    "IDLE_BRAKED.finish": 9,
+    "IDLE_BRAKED.resume": 9,
+    "IDLE_BRAKED.wait": 9,
+    "IDLE_BRAKED_SPOT.finish": 9,
+    "IDLE_BRAKED_SPOT.resume": 9,
+    "IDLE_BRAKED_SPOT.wait": 9,
+    "RETURNING.finish": 9,
+    "RETURNING.wait": 9,
+    "RETURNING_LATE.finish": 9,
+    "RETURNING_LATE.no": 9,
+    "RETURNING_LATE.wait": 9,
+    "RETURNING_LATE.yes": 9,
+    # Task 10
+    "ASKING_WAIT_TIME.yes": 10,
+    "CONFIRMING.navc": 10,
+    "CONFIRMING_CHANGE.navc": 10,
+    # Task 11
+    "AWAITING_USER.navc": 11,
+    "AWAITING_USER.navp": 11,
+    "TURNING.navc": 11,
+    # Task 12
+    "WAITING_ASKED.yes": 12,
+}
+
+
+def _cases():
+    for row, cells in EXPECT.items():
+        for col in COLS:
+            key = f"{row}.{col}"
+            marks = ()
+            if key in PENDING:
+                marks = (pytest.mark.xfail(strict=True, reason=f"Task {PENDING[key]}"),)
+            yield pytest.param(row, col, id=key, marks=marks)
+
+
+def test_table_covers_every_state_and_request():
+    """새 상태·새 요청이 생기면 표에서 빠지지 않게."""
+    reached = set()
+    for row, build in ROWS.items():
+        logic, _ = build()
+        reached.add(logic.state)
+        assert set(EXPECT[row]) == set(COLS), row
+    assert reached == set(State)
+    assert set(EXPECT) == set(ROWS)
+    assert set(REQUESTS) == set(COLS)
+    assert set(PENDING) <= {f"{r}.{c}" for r in EXPECT for c in COLS}
+
+
+@pytest.mark.parametrize("row,col", list(_cases()))
+def test_reaction(row, col):
+    logic, now = ROWS[row]()
+    actions = logic.on_voice_intent(REQUESTS[col], now, lookup, BOUNDS, True)
+    says = tuple(a.text for a in actions if isinstance(a, Say))
+    expected_says, expected_state = EXPECT[row][col]
+    assert (says, logic.state) == (expected_says, expected_state)
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected:  결과 줄: `3 failed, 894 passed, 1 skipped, 56 xfailed`

- [ ] **Step 3: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 894 passed, 1 skipped, 56 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 4: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/reaction_states.py src/vica_mission_manager/test/test_reaction_table.py
git -C vica_ros2_ws commit -m "test(mission): 미션 요청 반응표 230칸 시험 — 바꿀 56칸은 작업마다 푼다(strict xfail)" -m "$VICA_TRAILER"
```


### Task 3: 잠깐 — 질문 중이면 "네?", 일시정지 중이면 같은 말, 홈 복귀 중이면 세운다

규칙 1(틀린 이유를 고친다). `_react_by_table`에 상태별 처리기를 단다. 이번 작업은 "잠깐"(pause)만.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 확인 질문 | 잠깐 | “지금은 안내 중이 아닙니다.” → 확인 질문 | “네?” → 확인 질문 |
| 일시정지 | 잠깐 | “지금은 안내 중이 아닙니다.” → 일시정지 | “잠시 멈추겠습니다. 다시 출발하려면 말씀해 주세요.” → 일시정지 |
| 도착 질문 | 잠깐 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 도착 질문 | “네?” → 도착 질문 |
| 시간 질문 | 잠깐 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 시간 질문 | “네?” → 시간 질문 |
| 손 놓기 기다림 | 잠깐 | “지금은 안내 중이 아닙니다.” → 손 놓기 기다림 | “네?” → 손 놓기 기다림 |
| 접근 질문 | 잠깐 | “지금은 안내 중이 아닙니다.” → 접근 질문 | “네?” → 접근 질문 |
| 홈 복귀(안내 마친 뒤) | 잠깐 | “지금은 안내 중이 아닙니다.” → 홈 복귀 | “네?” → 안내 없음 |
| 홈 복귀(답이 없어 떠난 뒤) | 잠깐 | “지금은 안내 중이 아닙니다.” → 홈 복귀 | “네?” → 안내 없음 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: `MissionLogic._ask(text: str) -> Say` (expects_reply 질문 말)
- Produces: 처리기 `_react_confirming`·`_react_paused`·`_react_asking`·`_react_waiting`·`_react_awaiting_user`·`_react_returning`, 모두 `(intent, now, lookup, bounds, nav_ready) -> Optional[list]` — None 이면 옛 갈래

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/03-test.patch"
```

<details><summary>03-test.patch (20줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 56bf793..6e88b1c 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,15 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 3
-    "ASKING_NEXT.pause": 3,
-    "ASKING_WAIT_TIME.pause": 3,
-    "AWAITING_USER.pause": 3,
-    "CONFIRMING.pause": 3,
-    "PAUSED.pause": 3,
-    "RETURNING.pause": 3,
-    "RETURNING_LATE.pause": 3,
-    "WAITING_RELEASE.pause": 3,
     # Task 4
     "CONFIRMING.wait": 4,
     "CONFIRMING_CHANGE.wait": 4,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 8칸이 실패한다(값이 아직 옛 동작). 결과 줄: `11 failed, 894 passed, 1 skipped, 48 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/03-code.patch"
```

<details><summary>03-code.patch (77줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index 831c3d4..e0558f6 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1481,6 +1481,72 @@ class MissionLogic:
         nav_ready: bool,
     ) -> Optional[list]:
         """반응표로 새로 정한 칸(2026-10-08). 맡지 않는 칸은 None — 옛 갈래가 처리한다."""
+        handler = {
+            State.CONFIRMING: self._react_confirming,
+            State.PAUSED: self._react_paused,
+            State.ASKING_NEXT: self._react_asking,
+            State.ASKING_WAIT_TIME: self._react_asking,
+            State.WAITING_RELEASE: self._react_waiting,
+            State.AWAITING_USER: self._react_awaiting_user,
+            State.RETURNING: self._react_returning,
+        }.get(self.state)
+        if handler is None:
+            return None
+        return handler(intent, now, lookup, bounds, nav_ready)
+
+    @staticmethod
+    def _ask(text: str) -> Say:
+        """대답을 기다리는 말 — 노드가 듣기 창을 연다(expects_reply)."""
+        return Say(text, priority="response", expects_reply=True)
+
+    def _react_confirming(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """확인 질문. 잠깐 = "네?" 하고 질문을 그대로 둔다(규칙 1). 주행 중 바꾸기 질문의
+        잠깐은 지금처럼 일시정지다."""
+        kind = intent.intent
+        change = self._change_from is not None
+        if kind == "pause" and not change:
+            self._confirm_deadline = now + self.confirm_timeout_sec
+            return [self._ask(MSG_WAKE_GREETING)]
+        return None
+
+    def _react_paused(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """일시정지. 잠깐 = 선 채로 "잠시 멈추겠습니다…"를 다시(규칙 1, 옛 말은 "안내 중이
+        아닙니다"). 손 놓침 정지는 on_pause_request 가 보통 정지로 바꾼다."""
+        if intent.intent == "pause":
+            actions, reason = self.on_pause_request(now)
+            if reason == GateReason.OK:
+                return actions
+            return [Say(MSG_PAUSED, priority="response")]
+        return None
+
+    def _react_asking(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """도착 질문·시간 질문. 잠깐 = "네?" 하고 질문 유지 — 다시 묻기 기회를 쓰지 않는다
+        (규칙 1, 옛 말은 알아듣고도 "잘 듣지 못했습니다…")."""
+        if intent.intent == "pause":
+            self._response_deadline = None
+            self._asking_entered_at = now
+            return [self._ask(MSG_WAKE_GREETING)]
+        return None
+
+    def _react_waiting(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """손 놓기 기다림·대기 중. 손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고 듣는다 —
+        듣는 동안은 대기 장소로 떠나지 않는다(_ear_holds)."""
+        if intent.intent == "pause" and self.state == State.WAITING_RELEASE:
+            return [self._ask(MSG_WAKE_GREETING)]
+        return None
+
+    def _react_awaiting_user(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """접근 질문. 잠깐 = "네?" 하고 질문 유지, 답 시계를 지금부터 다시 센다."""
+        if intent.intent == "pause":
+            self._response_deadline = now + self.approach_response_timeout_sec
+            return [self._ask(MSG_WAKE_GREETING)]
+        return None
+
+    def _react_returning(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """홈 복귀. 잠깐 = "비카야"처럼 세우고 "네?"(규칙 1, 옛 말은 "안내 중이 아닙니다"로
+        못 세웠다). 관리자 홈 복귀의 잠깐은 지금처럼 일시정지다."""
+        if intent.intent == "pause" and not self._returning_home:
+            return self.on_return_brake(now) + [self._ask(MSG_WAKE_GREETING)]
         return None
 
     def _route_voice_intent(
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 902 passed, 1 skipped, 48 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "fix(mission): 잠깐을 상태마다 같은 뜻으로 — 질문 중 '네?'·일시정지 중 같은 말·홈 복귀 중 세우기(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 4: 기다려 — 버리지 않는다

규칙 1. 안내 주행 중 = 잠깐과 같이 멈춤, 일시정지 중 = 선 채로 같은 말, 확인 질문 = 아니요와 같음, 손 놓기
기다림·대기 중 = 시간을 지금부터 다시 세고 대기 안내(M2)를 다시, 그냥 쉬는 중 = 이유("지금은 안내 중이
아닙니다"). 홈 가다 세운 뒤의 "기다려"는 작업 9(결정 1)가 맡는다.

`test/test_reaction_rules.py`를 만든다 — 칸의 첫 반응 뒤에 이어지는 일(시간·문장 대조)을 본다.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 안내 없음 | 기다려 | (말 없음) → 안내 없음 | “지금은 안내 중이 아닙니다.” → 안내 없음 |
| 확인 질문 | 기다려 | (말 없음) → 확인 질문 | “안내 요청이 취소되었습니다.” → 안내 없음 |
| 주행 중 바꾸기 질문 | 기다려 | (말 없음) → 확인 질문 | “409호로 다시 출발합니다.” → 안내 주행 |
| 안내 주행 | 기다려 | (말 없음) → 안내 주행 | “잠시 멈추겠습니다. 다시 출발하려면 말씀해 주세요.” → 일시정지 |
| 일시정지 | 기다려 | (말 없음) → 일시정지 | “잠시 멈추겠습니다. 다시 출발하려면 말씀해 주세요.” → 일시정지 |
| 손 놓기 기다림 | 기다려 | (말 없음) → 손 놓기 기다림 | “10분 동안 입구 오른쪽에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 손 놓기 기다림 |
| 대기 중 | 기다려 | (말 없음) → 대기 중 | “10분 동안 입구 오른쪽에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 대기 중 |
| 대기 중 '어디로 모실까요?' 뒤 | 기다려 | (말 없음) → 대기 중 | “10분 동안 입구 오른쪽에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 대기 중 |

**Files:**
- Create: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: `_react_idle`, `_react_navigating`(새 처리기), `_rewait(minutes: int, now: float) -> list`
- Produces: `test/test_reaction_rules.py`(뒤 작업들이 이어 쓴다)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/04-test.patch"
```

<details><summary>04-test.patch (71줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
new file mode 100644
index 0000000..2d695d3
--- /dev/null
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -0,0 +1,45 @@
+"""반응표 칸 밖의 세부 — 시간·문장 대조·이어지는 동작 (미션 요청 반응표, 2026-10-08).
+
+칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
+"""
+from reaction_states import BOUNDS, intent, lookup, waiting, waiting_release
+from vica_mission_manager.mission_logic import (
+    MSG_WAIT_SPOT_CONFIRM,
+    NavStatus,
+    Say,
+    State,
+)
+
+
+def _says(actions):
+    return [a.text for a in actions if isinstance(a, Say)]
+
+
+# ---- Task 4: 기다려 ------------------------------------------------------------
+def test_waiting_wait_with_minutes_restarts_the_clock():
+    logic, t = waiting()
+    acts = logic.on_voice_intent(intent("wait", wait_minutes=20), t, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_SPOT_CONFIRM.format(minutes=20, place="입구 오른쪽")]
+    assert logic.state == State.WAITING
+    assert logic._wait_until == t + 20 * 60.0
+
+
+def test_waiting_wait_caps_at_30_minutes():
+    logic, t = waiting()
+    acts = logic.on_voice_intent(intent("wait", wait_minutes=45), t, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_SPOT_CONFIRM.format(minutes=30, place="입구 오른쪽")]
+    assert logic._wait_until == t + 30 * 60.0
+
+
+def test_release_waits_for_the_new_wait_sentence():
+    """손 놓기 기다림에서 시간을 바꾸면 새 안내를 다 말한 뒤에야 대기 장소로 떠난다."""
+    logic, t = waiting_release()
+    old = logic._release_text
+    acts = logic.on_voice_intent(intent("wait", wait_minutes=20), t, lookup, BOUNDS, True)
+    new = _says(acts)[0]
+    logic.on_wait_speech_spoken(old, t + 1.0)
+    assert logic.on_tick(t + 1.1, NavStatus.NONE) == []
+    assert logic.state == State.WAITING_RELEASE
+    logic.on_wait_speech_spoken(new, t + 6.0)
+    logic.on_tick(t + 6.1, NavStatus.NONE)
+    assert logic.state == State.MOVING_TO_WAIT_SPOT
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 6e88b1c..1aad1d5 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,15 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 4
-    "CONFIRMING.wait": 4,
-    "CONFIRMING_CHANGE.wait": 4,
-    "IDLE.wait": 4,
-    "NAVIGATING.wait": 4,
-    "PAUSED.wait": 4,
-    "WAITING.wait": 4,
-    "WAITING_ASKED.wait": 4,
-    "WAITING_RELEASE.wait": 4,
     # Task 5
     "CONFIRMING.finish": 5,
     "CONFIRMING_CHANGE.finish": 5,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 8칸과 새 시험 3개가 실패한다. 결과 줄: `14 failed, 902 passed, 1 skipped, 40 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/04-code.patch"
```

<details><summary>04-code.patch (104줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index e0558f6..29677e5 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1482,11 +1482,14 @@ class MissionLogic:
     ) -> Optional[list]:
         """반응표로 새로 정한 칸(2026-10-08). 맡지 않는 칸은 None — 옛 갈래가 처리한다."""
         handler = {
+            State.IDLE: self._react_idle,
             State.CONFIRMING: self._react_confirming,
+            State.NAVIGATING: self._react_navigating,
             State.PAUSED: self._react_paused,
             State.ASKING_NEXT: self._react_asking,
             State.ASKING_WAIT_TIME: self._react_asking,
             State.WAITING_RELEASE: self._react_waiting,
+            State.WAITING: self._react_waiting,
             State.AWAITING_USER: self._react_awaiting_user,
             State.RETURNING: self._react_returning,
         }.get(self.state)
@@ -1499,20 +1502,40 @@ class MissionLogic:
         """대답을 기다리는 말 — 노드가 듣기 창을 연다(expects_reply)."""
         return Say(text, priority="response", expects_reply=True)
 
+    def _react_idle(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """안내 없음. 그냥 쉬는 중의 기다려 = 이유를 말한다(규칙 1). 홈 가다 세운 뒤(복귀 재개
+        사다리)와 손잡이 잡기·온보딩 질문 중은 여기서 다루지 않는다."""
+        if (self._return_interrupted or self._grip_wait_since is not None
+                or self._dest_prompt_stage is not None):
+            return None
+        if intent.intent == "wait":
+            return [Say(MSG_NOT_NAVIGATING, priority="response")]
+        return None
+
     def _react_confirming(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """확인 질문. 잠깐 = "네?" 하고 질문을 그대로 둔다(규칙 1). 주행 중 바꾸기 질문의
-        잠깐은 지금처럼 일시정지다."""
+        """확인 질문. "네"만 출발이고 기다려는 "아니요"와 같다 — 대기·주행 중 바꾸기 질문이면
+        하던 대기·주행으로 돌아간다(규칙 1). 잠깐 = "네?" 하고 질문을 그대로 둔다. 주행 중
+        바꾸기 질문의 잠깐은 지금처럼 일시정지다."""
         kind = intent.intent
         change = self._change_from is not None
+        if kind == "wait":
+            dest = lookup(self.confirming_dest_id or "")
+            return self.on_confirm_answer(False, dest, bounds, nav_ready, now)
         if kind == "pause" and not change:
             self._confirm_deadline = now + self.confirm_timeout_sec
             return [self._ask(MSG_WAKE_GREETING)]
         return None
 
+    def _react_navigating(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """안내 주행. 기다려 = 잠깐과 같이 멈춘다(규칙 1)."""
+        if intent.intent == "wait":
+            return self._voice_mission_command("pause", now, nav_ready)
+        return None
+
     def _react_paused(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """일시정지. 잠깐 = 선 채로 "잠시 멈추겠습니다…"를 다시(규칙 1, 옛 말은 "안내 중이
-        아닙니다"). 손 놓침 정지는 on_pause_request 가 보통 정지로 바꾼다."""
-        if intent.intent == "pause":
+        """일시정지. 잠깐·기다려 = 선 채로 "잠시 멈추겠습니다…"를 다시(규칙 1, 옛 말은 "안내
+        중이 아닙니다"). 손 놓침 정지는 on_pause_request 가 보통 정지로 바꾼다."""
+        if intent.intent in ("pause", "wait"):
             actions, reason = self.on_pause_request(now)
             if reason == GateReason.OK:
                 return actions
@@ -1529,12 +1552,35 @@ class MissionLogic:
         return None
 
     def _react_waiting(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """손 놓기 기다림·대기 중. 손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고 듣는다 —
-        듣는 동안은 대기 장소로 떠나지 않는다(_ear_holds)."""
-        if intent.intent == "pause" and self.state == State.WAITING_RELEASE:
+        """손 놓기 기다림·대기 중. 기다려 = 시간을 지금부터 다시 세고 대기 안내를 다시 말한다.
+        손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고 듣는다 — 듣는 동안은 대기 장소로
+        떠나지 않는다(_ear_holds)."""
+        kind = intent.intent
+        if kind == "wait":
+            return self._rewait(intent.wait_minutes, now)
+        if kind == "pause" and self.state == State.WAITING_RELEASE:
             return [self._ask(MSG_WAKE_GREETING)]
         return None
 
+    def _rewait(self, minutes: int, now: float) -> list:
+        """대기 중 "기다려"·"20분 기다려" — 시간을 지금부터 다시 세고 대기 안내를 다시 말한다.
+        시간을 안 말했으면 처음 정한 시간 그대로다."""
+        if minutes is None or minutes <= 0:
+            minutes = (self._wait_minutes_requested if self._wait_minutes_requested > 0
+                       else WAIT_MINUTES_CAP)
+        minutes = min(int(minutes), WAIT_MINUTES_CAP)
+        self._wait_until = now + minutes * 60.0
+        self._wait_minutes_requested = minutes
+        place = self.wait_place
+        msg = (MSG_WAIT_SPOT_CONFIRM.format(minutes=minutes, place=place) if place
+               else MSG_WAIT_CONFIRM.format(minutes=minutes))
+        if self.state == State.WAITING_RELEASE:
+            # 손 놓기 판정은 새 안내를 다 말한 뒤부터다(on_wait_speech_spoken 이 이 글자와 대조).
+            self._release_text = msg
+            self._release_spoken_at = None
+            self._release_entered_at = now
+        return [Say(msg, priority="response")]
+
     def _react_awaiting_user(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
         """접근 질문. 잠깐 = "네?" 하고 질문 유지, 답 시계를 지금부터 다시 센다."""
         if intent.intent == "pause":
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 913 passed, 1 skipped, 40 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "fix(mission): 기다려를 버리지 않는다 — 안내 중 멈춤·확인 질문은 아니요·대기 중 시간 다시(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 5: 다 됐어 — 안내 중이면 취소처럼 되묻는다

규칙 1. 안내 주행·일시정지 = "안내를 취소할까요?"(두 번 말하면 취소 — "취소"와 같은 길), 확인 질문 =
아니요와 같음, 주행 중 바꾸기 질문 = "안내를 취소할까요?", 그냥 쉬는 중 = 이유. 홈 가다 세운 뒤·홈 복귀
중은 작업 9.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 안내 없음 | 다 됐어 | (말 없음) → 안내 없음 | “지금은 안내 중이 아닙니다.” → 안내 없음 |
| 확인 질문 | 다 됐어 | (말 없음) → 확인 질문 | “안내 요청이 취소되었습니다.” → 안내 없음 |
| 주행 중 바꾸기 질문 | 다 됐어 | (말 없음) → 확인 질문 | “안내를 취소할까요?” → 확인 질문 |
| 안내 주행 | 다 됐어 | (말 없음) → 안내 주행 | “안내를 취소할까요?” → 안내 주행 |
| 일시정지 | 다 됐어 | (말 없음) → 일시정지 | “안내를 취소할까요?” → 일시정지 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Consumes: `_voice_mission_command`(작업 1), 처리기들(작업 3·4)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/05-test.patch"
```

<details><summary>05-test.patch (48줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 2d695d3..ff24dad 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -2,8 +2,10 @@
 
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
-from reaction_states import BOUNDS, intent, lookup, waiting, waiting_release
+from reaction_states import BOUNDS, intent, lookup, navigating, waiting, waiting_release
 from vica_mission_manager.mission_logic import (
+    MSG_CANCEL_CONFIRM,
+    MSG_CANCELED,
     MSG_WAIT_SPOT_CONFIRM,
     NavStatus,
     Say,
@@ -43,3 +45,14 @@ def test_release_waits_for_the_new_wait_sentence():
     logic.on_wait_speech_spoken(new, t + 6.0)
     logic.on_tick(t + 6.1, NavStatus.NONE)
     assert logic.state == State.MOVING_TO_WAIT_SPOT
+
+
+# ---- Task 5: 다 됐어 -----------------------------------------------------------
+def test_navigating_finish_twice_cancels_like_cancel_twice():
+    """안내 주행 중 "다 됐어"는 "취소"와 같은 길 — 되물은 뒤 한 번 더 말하면 취소한다."""
+    logic, t = navigating()
+    first = logic.on_voice_intent(intent("finish"), t, lookup, BOUNDS, True)
+    assert _says(first) == [MSG_CANCEL_CONFIRM]
+    second = logic.on_voice_intent(intent("finish"), t + 2.0, lookup, BOUNDS, True)
+    assert MSG_CANCELED in _says(second)
+    assert logic.state == State.IDLE
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 1aad1d5..88bc2e4 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,12 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 5
-    "CONFIRMING.finish": 5,
-    "CONFIRMING_CHANGE.finish": 5,
-    "IDLE.finish": 5,
-    "NAVIGATING.finish": 5,
-    "PAUSED.finish": 5,
     # Task 6
     "ASKING_NEXT.resume": 6,
     "ASKING_WAIT_TIME.resume": 6,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 5칸과 새 시험 1개가 실패한다. 결과 줄: `9 failed, 913 passed, 1 skipped, 35 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/05-code.patch"
```

<details><summary>05-code.patch (61줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index 29677e5..78b1df5 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1503,22 +1503,25 @@ class MissionLogic:
         return Say(text, priority="response", expects_reply=True)
 
     def _react_idle(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """안내 없음. 그냥 쉬는 중의 기다려 = 이유를 말한다(규칙 1). 홈 가다 세운 뒤(복귀 재개
-        사다리)와 손잡이 잡기·온보딩 질문 중은 여기서 다루지 않는다."""
+        """안내 없음. 그냥 쉬는 중의 기다려·다 됐어 = 이유를 말한다(규칙 1). 홈 가다 세운 뒤
+        (복귀 재개 사다리)와 손잡이 잡기·온보딩 질문 중은 여기서 다루지 않는다."""
         if (self._return_interrupted or self._grip_wait_since is not None
                 or self._dest_prompt_stage is not None):
             return None
-        if intent.intent == "wait":
+        if intent.intent in ("wait", "finish"):
             return [Say(MSG_NOT_NAVIGATING, priority="response")]
         return None
 
     def _react_confirming(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """확인 질문. "네"만 출발이고 기다려는 "아니요"와 같다 — 대기·주행 중 바꾸기 질문이면
-        하던 대기·주행으로 돌아간다(규칙 1). 잠깐 = "네?" 하고 질문을 그대로 둔다. 주행 중
-        바꾸기 질문의 잠깐은 지금처럼 일시정지다."""
+        """확인 질문. "네"만 출발이고 기다려·다 됐어는 "아니요"와 같다 — 대기·주행 중 바꾸기
+        질문이면 하던 대기·주행으로 돌아간다(규칙 1). 주행 중 바꾸기 질문의 다 됐어는 안내
+        전체를 그만둘지 되묻는다. 잠깐 = "네?" 하고 질문을 그대로 둔다. 주행 중 바꾸기
+        질문의 잠깐은 지금처럼 일시정지다."""
         kind = intent.intent
         change = self._change_from is not None
-        if kind == "wait":
+        if kind == "finish" and change:
+            return self._voice_mission_command("cancel", now, nav_ready)
+        if kind in ("wait", "finish"):
             dest = lookup(self.confirming_dest_id or "")
             return self.on_confirm_answer(False, dest, bounds, nav_ready, now)
         if kind == "pause" and not change:
@@ -1527,14 +1530,20 @@ class MissionLogic:
         return None
 
     def _react_navigating(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """안내 주행. 기다려 = 잠깐과 같이 멈춘다(규칙 1)."""
-        if intent.intent == "wait":
+        """안내 주행. 기다려 = 잠깐과 같이 멈춘다, 다 됐어 = 취소처럼 되묻는다(규칙 1)."""
+        kind = intent.intent
+        if kind == "wait":
             return self._voice_mission_command("pause", now, nav_ready)
+        if kind == "finish":
+            return self._voice_mission_command("cancel", now, nav_ready)
         return None
 
     def _react_paused(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
         """일시정지. 잠깐·기다려 = 선 채로 "잠시 멈추겠습니다…"를 다시(규칙 1, 옛 말은 "안내
-        중이 아닙니다"). 손 놓침 정지는 on_pause_request 가 보통 정지로 바꾼다."""
+        중이 아닙니다"). 손 놓침 정지는 on_pause_request 가 보통 정지로 바꾼다. 다 됐어 =
+        취소처럼 되묻는다."""
+        if intent.intent == "finish":
+            return self._voice_mission_command("cancel", now, nav_ready)
         if intent.intent in ("pause", "wait"):
             actions, reason = self.on_pause_request(now)
             if reason == GateReason.OK:
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 919 passed, 1 skipped, 35 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "fix(mission): 다 됐어를 버리지 않는다 — 안내 중·일시정지는 취소 되묻기, 확인 질문은 아니요(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 6: 다시 가자 — 가는 중이면 가는 곳을, 도착 뒤·대기 중이면 "어디로 모실까요?"

규칙 1(틀린 이유 "다시 출발할 안내가 없습니다"를 고친다). 안내 주행 중 = "지금 OO로 가는 중이에요."
(음성 `replies.ALREADY_GOING`과 같은 글자, 새 상수 `MSG_ALREADY_GOING`), 확인 질문 = 같은 확인 질문 다시,
도착 질문·시간 질문 = "네, 어디로 모실까요?"로 질문을 바꾼다(그 질문의 아니요 = 종료·홈), 손 놓기 기다림·
대기 중 = "네, 어디로 모실까요?"(몇 번이든 묻기만), 접근 질문 = "네?" 하고 질문 유지.

확인 질문을 다시 하려면 미션이 그 문장을 알아야 한다 — 확인 질문에 들어가는 두 자리에서 `_confirm_prompt`를
남긴다.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 확인 질문 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 확인 질문 | “화장실로 안내해드릴까요?” → 확인 질문 |
| 안내 주행 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 안내 주행 | “지금 409호로 가는 중이에요.” → 안내 주행 |
| 도착 질문 | 다시 가자 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 도착 질문 | “네, 어디로 모실까요?” → 도착 질문 |
| 시간 질문 | 다시 가자 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 시간 질문 | “네, 어디로 모실까요?” → 도착 질문 |
| 손 놓기 기다림 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 손 놓기 기다림 | “네, 어디로 모실까요?” → 손 놓기 기다림 |
| 대기 중 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 대기 중 | “네, 어디로 모실까요?” → 대기 중 |
| 대기 중 '어디로 모실까요?' 뒤 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 대기 중 | “네, 어디로 모실까요?” → 대기 중 |
| 접근 질문 | 다시 가자 | “다시 출발할 안내가 없습니다.” → 접근 질문 | “네?” → 접근 질문 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 상수 `MSG_ALREADY_GOING = "지금 {name}{josa} 가는 중이에요."`
- Produces: 필드 `_confirm_prompt: str`, `_asking_where: bool`; `_confirm_prompt_for(dest) -> str`(static), `_ask_where(now) -> list`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/06-test.patch"
```

<details><summary>06-test.patch (83줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index ff24dad..8c7d1be 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -2,14 +2,20 @@
 
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
-from reaction_states import BOUNDS, intent, lookup, navigating, waiting, waiting_release
+from reaction_states import (BOUNDS, ELEV, asking, intent, lookup, navigating, waiting,
+                             waiting_release)
 from vica_mission_manager.mission_logic import (
+    MSG_ALREADY_GOING,
     MSG_CANCEL_CONFIRM,
     MSG_CANCELED,
+    MSG_FINISH,
+    MSG_START,
+    MSG_WAIT_FINISH_ASK,
     MSG_WAIT_SPOT_CONFIRM,
     NavStatus,
     Say,
     State,
+    say_destination,
 )
 
 
@@ -56,3 +62,36 @@ def test_navigating_finish_twice_cancels_like_cancel_twice():
     second = logic.on_voice_intent(intent("finish"), t + 2.0, lookup, BOUNDS, True)
     assert MSG_CANCELED in _says(second)
     assert logic.state == State.IDLE
+
+
+# ---- Task 6: 다시 가자 ---------------------------------------------------------
+def test_already_going_matches_the_voice_sentence():
+    """음성 replies.ALREADY_GOING("지금 {cur}{cur_josa} 가는 중이에요.")과 같은 글자."""
+    assert say_destination(MSG_ALREADY_GOING, "409호") == "지금 409호로 가는 중이에요."
+    assert say_destination(MSG_ALREADY_GOING, "식당") == "지금 식당으로 가는 중이에요."
+
+
+def test_asking_where_answers():
+    """도착 뒤 "다시 가자" → "네, 어디로 모실까요?" 다음의 답: 목적지 = 출발, 아니요 = 종료."""
+    logic, t = asking()
+    assert _says(logic.on_voice_intent(intent("resume"), t, lookup, BOUNDS, True)) == [
+        MSG_WAIT_FINISH_ASK]
+    acts = logic.on_voice_intent(intent(matched_destination_id=ELEV.id), t + 2, lookup,
+                                 BOUNDS, True)
+    assert _says(acts) == [say_destination(MSG_START, "엘리베이터")]
+    assert logic.state == State.NAVIGATING
+
+    logic, t = asking()
+    logic.on_voice_intent(intent("resume"), t, lookup, BOUNDS, True)
+    acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_FINISH]
+    assert logic.state == State.RETURNING
+
+
+def test_waiting_resume_twice_never_ends_the_guidance():
+    """대기 중 "다시 가자"는 몇 번이든 묻기만 한다 — 끝내기는 "다 됐어" 두 번뿐이다."""
+    logic, t = waiting()
+    for k in range(2):
+        acts = logic.on_voice_intent(intent("resume"), t + k, lookup, BOUNDS, True)
+        assert _says(acts) == [MSG_WAIT_FINISH_ASK]
+    assert logic.state == State.WAITING
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 88bc2e4..22ed2ca 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,15 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 6
-    "ASKING_NEXT.resume": 6,
-    "ASKING_WAIT_TIME.resume": 6,
-    "AWAITING_USER.resume": 6,
-    "CONFIRMING.resume": 6,
-    "NAVIGATING.resume": 6,
-    "WAITING.resume": 6,
-    "WAITING_ASKED.resume": 6,
-    "WAITING_RELEASE.resume": 6,
     # Task 7
     "ASKING_WAIT_TIME.no": 7,
     "AWAITING_USER.cancel": 7,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `test/test_reaction_rules.py` 수집 오류 — `ImportError: cannot import name 'MSG_ALREADY_GOING'`(아직 없는 상수). 결과 줄: `5c/scratchpad/proto/wt/tmpa1bcc_o3/r/vica_mission_manager/mission_logic.py)
=========================== short test summary info ============================
ERROR test/test_reaction_rules.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 skipped, 1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/06-code.patch"
```

<details><summary>06-code.patch (157줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index 78b1df5..ff96bc7 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -509,6 +509,9 @@ MSG_CANCEL_CONFIRM = "안내를 취소할까요?"
 MSG_CANCEL_KEPT = "안내를 계속하겠습니다."
 MSG_NOT_NAVIGATING = "지금은 안내 중이 아닙니다."
 MSG_NOT_PAUSED = "다시 출발할 안내가 없습니다."
+# 안내 주행 중 "다시 가자" — 이미 가는 중이다(미션 요청 반응표 2026-10-08). 음성
+# replies.ALREADY_GOING 과 같은 글자다 — 음성이 같은 말을 이미 합성해 쓴다.
+MSG_ALREADY_GOING = "지금 {name}{josa} 가는 중이에요."
 # 사람 접근. 질문은 되묻기와 같은 이유로 expects_reply 를 달아 내보낸다.
 # ⚠️ 문구 정본은 voice replies.py·ment_cache (approach-voice-flow.md 확정 흐름).
 # 글자까지 일치해야 사전 녹음이 재생된다 — 바꾸려면 양쪽을 함께 고치고
@@ -1363,6 +1366,7 @@ class MissionLogic:
         self._arrival_retried = False    # 무응답 재질문을 이미 한 번 했나
         self._asking_question = ""       # 지금 던져 둔 도착 질문(침묵 시 같은 질문을 다시 묻는다)
         self._deny_reconfirmed = False   # 대기형 질문의 거절을 종료형으로 되물었나 (2026-09-20)
+        self._asking_where = False       # 도착 질문을 "네, 어디로 모실까요?"로 바꿔 물었나 (2026-10-08)
         self._leaving_deadline: Optional[float] = None   # 떠나기 예고 유예
         self._wait_until: Optional[float] = None         # WAITING 만료 시각
         self._wait_minutes_requested = -1    # 대장(P1): 대기 요청 분. WAITING 밖에서는 -1
@@ -1391,6 +1395,8 @@ class MissionLogic:
         # 원래 가던 목적지를 여기 든다. 확정되면 새 목적지로, 거절·무응답·호출이면 이
         # 목적지로 다시 출발한다(_fold_confirming). 대기 보류(_wait_hold)와 같은 틀이다.
         self._change_from: Optional[Destination] = None
+        # 지금 확인 질문의 문장(2026-10-08 반응표). "다시 가자"·다시 묻기에서 같은 질문을 한다.
+        self._confirm_prompt = ""
         # 지금 안내 주행의 행동 트리 종류. 재시도·재개가 같은 트리를 쓰게 한다.
         self._nav_tree: str = NAV_TREE_DEFAULT
         # 귀 상태 (/vica/listen_state). 무응답 판정 전에 귀 사정을 본다.
@@ -1527,15 +1533,30 @@ class MissionLogic:
         if kind == "pause" and not change:
             self._confirm_deadline = now + self.confirm_timeout_sec
             return [self._ask(MSG_WAKE_GREETING)]
+        if kind == "resume" and not change and self._confirm_prompt:
+            # 물어 둔 질문에 "다시 가자" — 출발해도 되는지 같은 질문으로 다시 묻는다.
+            self._confirm_deadline = now + self.confirm_timeout_sec
+            return [self._ask(self._confirm_prompt)]
         return None
 
+    @staticmethod
+    def _confirm_prompt_for(dest: Optional[Destination]) -> str:
+        """목적지 확인 질문 문장. 목적지에 문장이 없으면 음성과 같은 기본 문장이다."""
+        if dest is None:
+            return ""
+        return dest.confirm_prompt or say_destination(MSG_CONFIRM_PROMPT_FALLBACK, dest.name)
+
     def _react_navigating(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """안내 주행. 기다려 = 잠깐과 같이 멈춘다, 다 됐어 = 취소처럼 되묻는다(규칙 1)."""
+        """안내 주행. 기다려 = 잠깐과 같이 멈춘다, 다 됐어 = 취소처럼 되묻는다, 다시 가자 =
+        이미 가는 중이라고 답한다(규칙 1, 옛 말은 "다시 출발할 안내가 없습니다")."""
         kind = intent.intent
         if kind == "wait":
             return self._voice_mission_command("pause", now, nav_ready)
         if kind == "finish":
             return self._voice_mission_command("cancel", now, nav_ready)
+        if kind == "resume" and self.active_destination is not None and not self._nav_from_app:
+            return [Say(say_destination(MSG_ALREADY_GOING, self.active_destination.name),
+                        priority="response")]
         return None
 
     def _react_paused(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
@@ -1552,12 +1573,28 @@ class MissionLogic:
         return None
 
     def _react_asking(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """도착 질문·시간 질문. 잠깐 = "네?" 하고 질문 유지 — 다시 묻기 기회를 쓰지 않는다
-        (규칙 1, 옛 말은 알아듣고도 "잘 듣지 못했습니다…")."""
-        if intent.intent == "pause":
+        """도착 질문·시간 질문. 잠깐 = "네?" 하고 질문 유지 — 다시 묻기 기회를 쓰지 않는다.
+        다시 가자 = "네, 어디로 모실까요?"로 묻는다(규칙 1, 옛 말은 알아듣고도 "잘 듣지
+        못했습니다…"). 그 질문의 아니요 = 안내 종료, 네 = 못 알아들은 답이다."""
+        kind = intent.intent
+        if kind == "pause":
             self._response_deadline = None
             self._asking_entered_at = now
             return [self._ask(MSG_WAKE_GREETING)]
+        if kind == "resume":
+            self.state = State.ASKING_NEXT
+            self._asking_where = True
+            self._asking_is_finish = False
+            self._asking_time_after_yes = False
+            self._asking_question = MSG_WAIT_FINISH_ASK
+            self._response_deadline = None
+            self._asking_entered_at = now
+            return [self._ask(MSG_WAIT_FINISH_ASK)]
+        if self._asking_where and kind in ("affirm", "deny"):
+            if kind == "deny":
+                self._reset_arrival_dialog()
+                return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
+            return self._arrival_no_answer(now)
         return None
 
     def _react_waiting(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
@@ -1567,10 +1604,18 @@ class MissionLogic:
         kind = intent.intent
         if kind == "wait":
             return self._rewait(intent.wait_minutes, now)
+        if kind == "resume":
+            return self._ask_where(now)
         if kind == "pause" and self.state == State.WAITING_RELEASE:
             return [self._ask(MSG_WAKE_GREETING)]
         return None
 
+    def _ask_where(self, now: float) -> list:
+        """대기 중 "다시 가자" — 어디로 갈지 묻는다. "다 됐어"의 첫 질문과 같은 문장이지만
+        두 번 말해도 안내를 끝내지 않는다(그건 "다 됐어"만)."""
+        self._wait_finish_asked_at = now
+        return [self._ask(MSG_WAIT_FINISH_ASK)]
+
     def _rewait(self, minutes: int, now: float) -> list:
         """대기 중 "기다려"·"20분 기다려" — 시간을 지금부터 다시 세고 대기 안내를 다시 말한다.
         시간을 안 말했으면 처음 정한 시간 그대로다."""
@@ -1591,8 +1636,8 @@ class MissionLogic:
         return [Say(msg, priority="response")]
 
     def _react_awaiting_user(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """접근 질문. 잠깐 = "네?" 하고 질문 유지, 답 시계를 지금부터 다시 센다."""
-        if intent.intent == "pause":
+        """접근 질문. 잠깐·다시 가자 = "네?" 하고 질문 유지, 답 시계를 지금부터 다시 센다."""
+        if intent.intent in ("pause", "resume"):
             self._response_deadline = now + self.approach_response_timeout_sec
             return [self._ask(MSG_WAKE_GREETING)]
         return None
@@ -1745,6 +1790,7 @@ class MissionLogic:
                 self.state = State.CONFIRMING
                 self._confirming_dest_id = intent.matched_destination_id or None
                 self._confirm_deadline = now + self.confirm_timeout_sec
+                self._confirm_prompt = self._confirm_prompt_for(dest)
                 return []
 
         # need_confirm == false (확정 요청)
@@ -1870,6 +1916,7 @@ class MissionLogic:
         self.state = State.CONFIRMING
         self._confirming_dest_id = new_id
         self._confirm_deadline = now + self.confirm_timeout_sec
+        self._confirm_prompt = self._confirm_prompt_for(dest)
         # 앞서 물은 "안내를 취소할까요?"는 이 질문으로 대체됐다 — 남기면 새 목적지로
         # 출발한 뒤 "취소" 한마디가 되묻지 않고 바로 취소된다(2026-10-07 검토).
         self.cancel_confirm_pending = False
@@ -2801,6 +2848,7 @@ class MissionLogic:
         self._arrival_retried = False
         self._asking_question = question
         self._deny_reconfirmed = False
+        self._asking_where = False
         self._leaving_deadline = None
         self._response_deadline = None   # 재생완료(on_arrival_question_spoken)에서 시작
         text = f"{arrival_text} {question}".strip() if arrival_text else question
@@ -3422,6 +3470,7 @@ class MissionLogic:
         self._arrival_retried = False
         self._asking_question = ""
         self._deny_reconfirmed = False
+        self._asking_where = False
         self._leaving_deadline = None
         self._wait_until = None
         self._wait_minutes_requested = -1
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 930 passed, 1 skipped, 27 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "fix(mission): 다시 가자에 맞는 답 — 가는 중이면 가는 곳, 도착 뒤·대기 중이면 어디로 모실까요(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 7: 아니요·취소 — 끝낼지 한 번 확인하고, 취소 확인의 네·아니요를 받는다

규칙 1. 시간 질문의 아니요·손 놓기 기다림의 아니요·취소 = "여기까지 안내를 마칠까요?"(종료형, 네 = 종료·
홈, 아니요 = 하던 대기 시간 그대로 다시), 대기 중 "어디로 모실까요?" 뒤 30초 안의 아니요 = 종료·홈, 확인
질문의 취소 = 아니요와 같음, 접근 질문의 취소 = 아니요(물러난다). 그리고 "안내를 취소할까요?"의 네·아니요를
미션이 받는다 — 예전엔 접근 질문 배선으로 가서 버려졌다(아니요 = "안내를 계속하겠습니다.").

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 확인 질문 | 취소 | “지금은 안내 중이 아닙니다.” → 확인 질문 | “안내 요청이 취소되었습니다.” → 안내 없음 |
| 시간 질문 | 아니요 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 시간 질문 | “여기까지 안내를 마칠까요?” → 도착 질문 |
| 손 놓기 기다림 | 취소 | “지금은 안내 중이 아닙니다.” → 손 놓기 기다림 | “여기까지 안내를 마칠까요?” → 도착 질문 |
| 손 놓기 기다림 | 아니요 | (말 없음) → 손 놓기 기다림 | “여기까지 안내를 마칠까요?” → 도착 질문 |
| 대기 중 '어디로 모실까요?' 뒤 | 아니요 | (말 없음) → 대기 중 | “안내를 종료합니다.” → 홈 복귀 |
| 접근 질문 | 취소 | “지금은 안내 중이 아닙니다.” → 접근 질문 | “알겠습니다. 이만 물러납니다.” → 홈 복귀 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: `_ask_end_confirm(now: float) -> list`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/07-test.patch"
```

<details><summary>07-test.patch (94줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 8c7d1be..322a57e 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -2,14 +2,17 @@
 
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
-from reaction_states import (BOUNDS, ELEV, asking, intent, lookup, navigating, waiting,
-                             waiting_release)
+from reaction_states import (BOUNDS, ELEV, asking, asking_wait_time, intent, lookup,
+                             navigating, waiting, waiting_asked, waiting_release)
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
+    MSG_ASK_ENTRANCE,
+    MSG_CANCEL_KEPT,
     MSG_CANCEL_CONFIRM,
     MSG_CANCELED,
     MSG_FINISH,
     MSG_START,
+    MSG_WAIT_DEFAULT,
     MSG_WAIT_FINISH_ASK,
     MSG_WAIT_SPOT_CONFIRM,
     NavStatus,
@@ -95,3 +98,51 @@ def test_waiting_resume_twice_never_ends_the_guidance():
         acts = logic.on_voice_intent(intent("resume"), t + k, lookup, BOUNDS, True)
         assert _says(acts) == [MSG_WAIT_FINISH_ASK]
     assert logic.state == State.WAITING
+
+
+# ---- Task 7: 아니요·취소 -------------------------------------------------------
+def test_release_no_then_answers():
+    """M2 직후 "아니(기다리지 마)" → "마칠까요?" → 네 = 종료·홈, 아니요 = 하던 대기 그대로."""
+    logic, t = waiting_release(minutes=10)
+    assert _says(logic.on_voice_intent(intent("deny"), t, lookup, BOUNDS, True)) == [
+        MSG_ASK_ENTRANCE]
+    acts = logic.on_voice_intent(intent("affirm"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_FINISH]
+    assert logic.state == State.RETURNING
+
+    logic, t = waiting_release(minutes=10)
+    logic.on_voice_intent(intent("deny"), t, lookup, BOUNDS, True)
+    acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_SPOT_CONFIRM.format(minutes=10, place="입구 오른쪽")]
+    assert logic.state == State.WAITING_RELEASE
+
+
+def test_wait_time_no_then_answers():
+    logic, t = asking_wait_time()
+    assert _says(logic.on_voice_intent(intent("deny"), t, lookup, BOUNDS, True)) == [
+        MSG_ASK_ENTRANCE]
+    acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_DEFAULT]
+    assert logic.state == State.WAITING
+
+
+def test_cancel_question_yes_and_no():
+    """"안내를 취소할까요?"의 네·아니요 — 예전엔 둘 다 버려졌다."""
+    logic, t = navigating()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_CANCEL_KEPT]
+    assert logic.state == State.NAVIGATING and not logic.cancel_confirm_pending
+
+    logic, t = navigating()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    acts = logic.on_voice_intent(intent("affirm"), t + 2, lookup, BOUNDS, True)
+    assert MSG_CANCELED in _says(acts)
+    assert logic.state == State.IDLE
+
+
+def test_waiting_no_after_the_window_is_not_an_answer():
+    logic, t = waiting_asked()
+    acts = logic.on_voice_intent(intent("deny"), t + 31.0, lookup, BOUNDS, True)
+    assert _says(acts) == []
+    assert logic.state == State.WAITING
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 22ed2ca..810a141 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,13 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 7
-    "ASKING_WAIT_TIME.no": 7,
-    "AWAITING_USER.cancel": 7,
-    "CONFIRMING.cancel": 7,
-    "WAITING_ASKED.no": 7,
-    "WAITING_RELEASE.cancel": 7,
-    "WAITING_RELEASE.no": 7,
     # Task 8
     "WAITING.cancel": 8,
     "WAITING_ASKED.cancel": 8,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 6칸과 새 시험 3개가 실패한다(대기 창 밖 아니요 시험은 지금도 통과). 결과 줄: `12 failed, 931 passed, 1 skipped, 21 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/07-code.patch"
```

<details><summary>07-code.patch (110줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index ff96bc7..c3cc1c0 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1487,6 +1487,9 @@ class MissionLogic:
         nav_ready: bool,
     ) -> Optional[list]:
         """반응표로 새로 정한 칸(2026-10-08). 맡지 않는 칸은 None — 옛 갈래가 처리한다."""
+        if self.cancel_confirm_pending and intent.intent in ("affirm", "deny"):
+            # "안내를 취소할까요?"의 네·아니요 — 예전엔 접근 질문 배선으로 가서 버려졌다.
+            return self.on_cancel_confirm_answer(intent.intent == "affirm", now)
         handler = {
             State.IDLE: self._react_idle,
             State.CONFIRMING: self._react_confirming,
@@ -1519,15 +1522,15 @@ class MissionLogic:
         return None
 
     def _react_confirming(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """확인 질문. "네"만 출발이고 기다려·다 됐어는 "아니요"와 같다 — 대기·주행 중 바꾸기
-        질문이면 하던 대기·주행으로 돌아간다(규칙 1). 주행 중 바꾸기 질문의 다 됐어는 안내
+        """확인 질문. "네"만 출발이고 기다려·다 됐어·취소는 "아니요"와 같다 — 대기·주행 중
+        바꾸기 질문이면 하던 대기·주행으로 돌아간다(규칙 1). 주행 중 바꾸기 질문의 다 됐어는 안내
         전체를 그만둘지 되묻는다. 잠깐 = "네?" 하고 질문을 그대로 둔다. 주행 중 바꾸기
         질문의 잠깐은 지금처럼 일시정지다."""
         kind = intent.intent
         change = self._change_from is not None
         if kind == "finish" and change:
             return self._voice_mission_command("cancel", now, nav_ready)
-        if kind in ("wait", "finish"):
+        if kind in ("wait", "finish") or (kind == "cancel" and not change):
             dest = lookup(self.confirming_dest_id or "")
             return self.on_confirm_answer(False, dest, bounds, nav_ready, now)
         if kind == "pause" and not change:
@@ -1595,19 +1598,49 @@ class MissionLogic:
                 self._reset_arrival_dialog()
                 return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
             return self._arrival_no_answer(now)
+        if self.state == State.ASKING_WAIT_TIME and kind == "deny":
+            # "몇 분쯤 걸리실까요?"에 "아니(기다리지 마)" — 끝낼지 한 번 확인한다.
+            return self._ask_end_confirm(now)
         return None
 
+    def _ask_end_confirm(self, now: float) -> list:
+        """끝낼지 한 번 확인한다 — "여기까지 안내를 마칠까요?"(종료형). 네 = 종료·홈, 아니요 =
+        대기, 침묵 = 같은 질문 한 번 더 뒤 떠나기 예고(도착 질문의 무응답 사다리 그대로)."""
+        self.state = State.ASKING_NEXT
+        self._deny_reconfirmed = True
+        self._asking_is_finish = True
+        self._asking_time_after_yes = False
+        self._asking_where = False
+        self._asking_question = MSG_ASK_ENTRANCE
+        self._arrival_retried = False
+        self._leaving_deadline = None
+        self._response_deadline = None
+        self._asking_entered_at = now
+        return [self._ask(MSG_ASK_ENTRANCE)]
+
     def _react_waiting(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
         """손 놓기 기다림·대기 중. 기다려 = 시간을 지금부터 다시 세고 대기 안내를 다시 말한다.
-        손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고 듣는다 — 듣는 동안은 대기 장소로
-        떠나지 않는다(_ear_holds)."""
+        다시 가자 = 어디로 갈지 묻는다. 손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고
+        듣는다 — 듣는 동안은 대기 장소로 떠나지 않는다(_ear_holds). 손 놓기 기다림의
+        아니요·취소 = 끝낼지 확인. 대기 중 "어디로 모실까요?" 뒤 30초 안의 아니요 = 종료."""
         kind = intent.intent
+        release = self.state == State.WAITING_RELEASE
         if kind == "wait":
             return self._rewait(intent.wait_minutes, now)
         if kind == "resume":
             return self._ask_where(now)
-        if kind == "pause" and self.state == State.WAITING_RELEASE:
-            return [self._ask(MSG_WAKE_GREETING)]
+        if release:
+            if kind == "pause":
+                return [self._ask(MSG_WAKE_GREETING)]
+            if kind in ("cancel", "deny"):
+                # 대기 안내(M2) 바로 뒤 "아니, 기다리지 마"·"취소" — 끝낼지 한 번 확인한다.
+                return self._ask_end_confirm(now)
+            return None
+        asked = self._wait_finish_asked_at
+        if kind == "deny" and asked is not None and now - asked <= WAIT_FINISH_REPEAT_SEC:
+            # "네, 어디로 모실까요?"에 "아니" — 갈 곳이 없다. "다 됐어"를 두 번 한 것과 같다.
+            self._reset_arrival_dialog()
+            return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
         return None
 
     def _ask_where(self, now: float) -> list:
@@ -1636,7 +1669,10 @@ class MissionLogic:
         return [Say(msg, priority="response")]
 
     def _react_awaiting_user(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """접근 질문. 잠깐·다시 가자 = "네?" 하고 질문 유지, 답 시계를 지금부터 다시 센다."""
+        """접근 질문. 취소 = 아니요(물러난다). 잠깐·다시 가자 = "네?" 하고 질문 유지, 답 시계를
+        지금부터 다시 센다."""
+        if intent.intent == "cancel":
+            return self.on_approach_answer(False, now)
         if intent.intent in ("pause", "resume"):
             self._response_deadline = now + self.approach_response_timeout_sec
             return [self._ask(MSG_WAKE_GREETING)]
@@ -3135,6 +3171,10 @@ class MissionLogic:
         # deny: 종료형이면 "안 끝났다"=대기, 대기형이면 "대기 싫다"=종료.
         if kind == "deny":
             if self._asking_is_finish:
+                if self._wait_minutes_requested > 0:
+                    # 대기 중 "기다리지 마"를 끝낼지 되물은 질문의 "아니요" — 하던 대기 시간
+                    # 그대로 다시 기다린다(2026-10-08 반응표).
+                    return self._enter_waiting(self._wait_minutes_requested, now)
                 return self._enter_waiting(WAIT_MINUTES_CAP, now,
                                            default_msg=True)
             if not self._deny_reconfirmed:
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 940 passed, 1 skipped, 21 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "fix(mission): 아니요·취소 — 시간 질문·M2 뒤는 마칠까요로 확인, 취소 확인의 네·아니요를 받는다(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 8: 결정 3 — 대기 중 취소는 "안내가 필요 없으신가요?"

사용자 결정 3(사용자 문구). 부정 질문이라 네(필요 없다)·다 됐어·두 번째 취소 = 종료·홈, 아니요(필요하다) =
"안내를 계속하겠습니다." 하고 계속 기다린다. 대기 중의 옛 "안내를 취소할까요?"(취소 뒤 그 자리에 서던 동작)는
음성 요청에서 더 쓰지 않는다 — 앱 취소는 그대로.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 대기 중 | 취소 | “안내를 취소할까요?” → 대기 중 | “안내가 필요 없으신가요?” → 대기 중 |
| 대기 중 '어디로 모실까요?' 뒤 | 취소 | “안내를 취소할까요?” → 대기 중 | “안내가 필요 없으신가요?” → 대기 중 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 상수 `MSG_WAIT_NEED_ASK = "안내가 필요 없으신가요?"`, 필드 `_wait_need_asked_at`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/08-test.patch"
```

<details><summary>08-test.patch (52줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 322a57e..79a369e 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -14,6 +14,7 @@ from vica_mission_manager.mission_logic import (
     MSG_START,
     MSG_WAIT_DEFAULT,
     MSG_WAIT_FINISH_ASK,
+    MSG_WAIT_NEED_ASK,
     MSG_WAIT_SPOT_CONFIRM,
     NavStatus,
     Say,
@@ -146,3 +147,25 @@ def test_waiting_no_after_the_window_is_not_an_answer():
     acts = logic.on_voice_intent(intent("deny"), t + 31.0, lookup, BOUNDS, True)
     assert _says(acts) == []
     assert logic.state == State.WAITING
+
+
+# ---- Task 8: 결정 3 — 대기 중 취소 ---------------------------------------------
+def test_need_question_is_the_users_sentence():
+    assert MSG_WAIT_NEED_ASK == "안내가 필요 없으신가요?"
+
+
+def test_need_question_answers():
+    """부정 질문: 네(필요 없다)·다 됐어·두 번째 취소 = 종료·홈, 아니요(필요하다) = 계속 대기."""
+    for answer in ("affirm", "finish", "cancel"):
+        logic, t = waiting()
+        assert _says(logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)) == [
+            MSG_WAIT_NEED_ASK]
+        acts = logic.on_voice_intent(intent(answer), t + 2, lookup, BOUNDS, True)
+        assert _says(acts) == [MSG_FINISH], answer
+        assert logic.state == State.RETURNING, answer
+
+    logic, t = waiting()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_CANCEL_KEPT]
+    assert logic.state == State.WAITING
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 810a141..9fb6002 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,9 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 8
-    "WAITING.cancel": 8,
-    "WAITING_ASKED.cancel": 8,
     # Task 9
     "IDLE_BRAKED.finish": 9,
     "IDLE_BRAKED.resume": 9,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `test/test_reaction_rules.py` 수집 오류 — `ImportError: cannot import name 'MSG_WAIT_NEED_ASK'`. 결과 줄: `5c/scratchpad/proto/wt/tmp_4jsiwp4/r/vica_mission_manager/mission_logic.py)
=========================== short test summary info ============================
ERROR test/test_reaction_rules.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 skipped, 1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/08-code.patch"
```

<details><summary>08-code.patch (67줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index c3cc1c0..ce13771 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -451,6 +451,9 @@ MSG_WAIT_EXPIRED = "대기 시간이 종료되어 제자리로 돌아갑니다."
 # 정해져 출발할 때 끝나므로(호출 반응표) 묻기만 한다. 다음 목적지를 미리 아는 기능이
 # 생기면 "OO으로 갈까요?"로 바꾼다(미구현).
 MSG_WAIT_FINISH_ASK = "네, 어디로 모실까요?"
+# 대기 중 "취소" — 안내를 끝낼지 묻는다(2026-10-08 사용자 결정 3, 사용자 문구). 부정 질문이라
+# "네"(필요 없다) = 종료·홈, "아니요"(필요하다) = 계속 대기. 음성 쪽이 미리 굽는 글자와 같아야 한다.
+MSG_WAIT_NEED_ASK = "안내가 필요 없으신가요?"
 # 대기 장소 입구 기준 방향 → 멘트 속 장소 말. 상황판(RobotState.wait_place)에도 같은 말을 쓴다.
 WAIT_PLACE_PHRASES = {"right": "입구 오른쪽", "left": "입구 왼쪽", "across": "입구 맞은편"}
 # 대기 장소가 막혀 목적지로 돌아와 기다릴 때의 장소 말.
@@ -1387,6 +1390,7 @@ class MissionLogic:
         self._release_spoken_at: Optional[float] = None
         self._release_entered_at: Optional[float] = None
         self._wait_finish_asked_at: Optional[float] = None   # 대기 중 "어디로 모실까요?" 시각
+        self._wait_need_asked_at: Optional[float] = None     # 대기 중 "안내가 필요 없으신가요?" 시각
         # 대기 중에 목적지 '제안'이 와서 확인 질문(CONFIRMING)으로 들어갔을 때 돌아갈
         # 대기 상태. 거절·시간초과·호출이면 이 상태로 되돌아간다(대기 시간·장소 유지).
         self._wait_hold: Optional[State] = None
@@ -1622,7 +1626,8 @@ class MissionLogic:
         """손 놓기 기다림·대기 중. 기다려 = 시간을 지금부터 다시 세고 대기 안내를 다시 말한다.
         다시 가자 = 어디로 갈지 묻는다. 손 놓기 기다림의 잠깐 = "비카야"처럼 "네?" 하고
         듣는다 — 듣는 동안은 대기 장소로 떠나지 않는다(_ear_holds). 손 놓기 기다림의
-        아니요·취소 = 끝낼지 확인. 대기 중 "어디로 모실까요?" 뒤 30초 안의 아니요 = 종료."""
+        아니요·취소 = 끝낼지 확인. 대기 중 취소 = "안내가 필요 없으신가요?"(결정 3). 대기 중
+        "어디로 모실까요?" 뒤 30초 안의 아니요 = 종료."""
         kind = intent.intent
         release = self.state == State.WAITING_RELEASE
         if kind == "wait":
@@ -1636,6 +1641,18 @@ class MissionLogic:
                 # 대기 안내(M2) 바로 뒤 "아니, 기다리지 마"·"취소" — 끝낼지 한 번 확인한다.
                 return self._ask_end_confirm(now)
             return None
+        if self._wait_need_asked_at is not None and kind in ("affirm", "deny", "cancel", "finish"):
+            # "안내가 필요 없으신가요?"의 답(결정 3). 부정 질문이라 네(필요 없다)·다 됐어·두 번째
+            # 취소 = 종료·홈, 아니요(필요하다) = 계속 기다린다.
+            self._wait_need_asked_at = None
+            if kind == "deny":
+                return [Say(MSG_CANCEL_KEPT, priority="response")]
+            self._reset_arrival_dialog()
+            return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
+        if kind == "cancel":
+            self._wait_need_asked_at = now
+            self._wait_finish_asked_at = None
+            return [self._ask(MSG_WAIT_NEED_ASK)]
         asked = self._wait_finish_asked_at
         if kind == "deny" and asked is not None and now - asked <= WAIT_FINISH_REPEAT_SEC:
             # "네, 어디로 모실까요?"에 "아니" — 갈 곳이 없다. "다 됐어"를 두 번 한 것과 같다.
@@ -1647,6 +1664,7 @@ class MissionLogic:
         """대기 중 "다시 가자" — 어디로 갈지 묻는다. "다 됐어"의 첫 질문과 같은 문장이지만
         두 번 말해도 안내를 끝내지 않는다(그건 "다 됐어"만)."""
         self._wait_finish_asked_at = now
+        self._wait_need_asked_at = None
         return [self._ask(MSG_WAIT_FINISH_ASK)]
 
     def _rewait(self, minutes: int, now: float) -> list:
@@ -3523,6 +3541,7 @@ class MissionLogic:
         self._release_spoken_at = None
         self._release_entered_at = None
         self._wait_finish_asked_at = None
+        self._wait_need_asked_at = None
         self._wait_hold = None
 
     def _forget_interrupted_return(self) -> None:
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 944 passed, 1 skipped, 19 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "feat(mission): 대기 중 취소는 '안내가 필요 없으신가요?'로 묻는다 — 사용자 결정 3" -m "$VICA_TRAILER"
```


### Task 9: 결정 1 — 홈 가는 중의 "기다려"는 직전 목적지 대기 장소로

사용자 결정 1과 덧붙인 것. 미션이 마지막으로 사용자와 도착한 목적지를 `_last_guided`로 기억한다(홈으로
떠나도 남기고, 홈 도착·새 안내·안내 뒤가 아닌 복귀·비상에서 지운다). 홈 가는 중 "기다려"와 "비카야"로 세운
뒤의 "기다려"는 그 목적지 대기 장소로 간다 — M2′를 말하고 손 놓기 판정 뒤 떠난다(손잡이를 안 잡고 있으니 말이
끝나면 바로). 대기 장소가 없으면 그 입구 앞으로(MOVING_BACK_TO_DEST, "최대 30분 동안 입구 앞에서…"),
직전 목적지가 없으면 그 자리에서.

10-07에 정했던 "복귀 중 '기다려 줘'는 그 자리에서 기다린다"(`_enter_returning` 주석)를 바꾸는 일이라 그 주석도
고친다. 답이 없어 떠난 뒤 늦게 온 네·아니요는 그 질문의 뜻대로(대기형: 네 = 대기·아니요 = "안내를 종료합니다"
하고 그대로 홈, 종료형: 반대). 홈 가는 중 "다 됐어" = 한마디 하고 그대로 홈, 세운 뒤의 "다 됐어"·"다시 가" =
"안내를 종료합니다" 하고 15초를 기다리지 않고 바로 홈.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 홈 가다 세운 뒤(대기 장소 없는 목적지) | 기다려 | (말 없음) → 안내 없음 | “최대 30분 동안 입구 앞에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 목적지로 되돌아감 |
| 홈 가다 세운 뒤(대기 장소 없는 목적지) | 다 됐어 | (말 없음) → 안내 없음 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 가다 세운 뒤(대기 장소 없는 목적지) | 다시 가자 | “다시 출발할 안내가 없습니다.” → 안내 없음 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 가다 세운 뒤(대기 장소 있는 목적지) | 기다려 | (말 없음) → 안내 없음 | “최대 30분 동안 입구 오른쪽에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 손 놓기 기다림 |
| 홈 가다 세운 뒤(대기 장소 있는 목적지) | 다 됐어 | (말 없음) → 안내 없음 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 가다 세운 뒤(대기 장소 있는 목적지) | 다시 가자 | “다시 출발할 안내가 없습니다.” → 안내 없음 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 복귀(안내 마친 뒤) | 기다려 | “네, 최대 30분까지 여기서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 대기 중 | “최대 30분 동안 입구 앞에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 목적지로 되돌아감 |
| 홈 복귀(안내 마친 뒤) | 다 됐어 | (말 없음) → 홈 복귀 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 복귀(답이 없어 떠난 뒤) | 기다려 | “네, 최대 30분까지 여기서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 대기 중 | “최대 30분 동안 입구 앞에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 목적지로 되돌아감 |
| 홈 복귀(답이 없어 떠난 뒤) | 다 됐어 | (말 없음) → 홈 복귀 | “안내를 종료합니다.” → 홈 복귀 |
| 홈 복귀(답이 없어 떠난 뒤) | 네 | (말 없음) → 홈 복귀 | “최대 30분 동안 입구 앞에서 기다리겠습니다. 돌아오시면 '비카야'라고 불러 주세요.” → 목적지로 되돌아감 |
| 홈 복귀(답이 없어 떠난 뒤) | 아니요 | (말 없음) → 홈 복귀 | “안내를 종료합니다.” → 홈 복귀 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 필드 `_last_guided: Optional[Destination]`, `_late_answer_finish: Optional[bool]`
- Produces: `_wait_at_last_guided(minutes: int, now: float) -> list`, `_enter_waiting(minutes, now, default_msg=False, away=False)`(away 추가)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/09-test.patch"
```

<details><summary>09-test.patch (107줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 79a369e..ec26dcd 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -2,8 +2,9 @@
 
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
-from reaction_states import (BOUNDS, ELEV, asking, asking_wait_time, intent, lookup,
-                             navigating, waiting, waiting_asked, waiting_release)
+from reaction_states import (BOUNDS, ELEV, SPOT_DEST, asking, asking_wait_time, idle_braked,
+                             intent, lookup, navigating, returning, returning_late, waiting,
+                             waiting_asked, waiting_release)
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
     MSG_ASK_ENTRANCE,
@@ -16,6 +17,9 @@ from vica_mission_manager.mission_logic import (
     MSG_WAIT_FINISH_ASK,
     MSG_WAIT_NEED_ASK,
     MSG_WAIT_SPOT_CONFIRM,
+    MSG_WAIT_SPOT_DEFAULT,
+    CancelNav,
+    Navigate,
     NavStatus,
     Say,
     State,
@@ -169,3 +173,56 @@ def test_need_question_answers():
     acts = logic.on_voice_intent(intent("deny"), t + 2, lookup, BOUNDS, True)
     assert _says(acts) == [MSG_CANCEL_KEPT]
     assert logic.state == State.WAITING
+
+
+# ---- Task 9: 결정 1 — 홈 가는 중의 "기다려" ------------------------------------
+def test_returning_wait_goes_back_to_the_wait_spot():
+    """대기 장소가 있는 목적지에서 안내를 마치고 홈 가는 중 "기다려" → 복귀를 멈추고 M2′ →
+    말이 끝나면 대기 장소로 떠난다."""
+    logic, t = returning(SPOT_DEST)
+    acts = logic.on_voice_intent(intent("wait"), t, lookup, BOUNDS, True)
+    assert any(isinstance(a, CancelNav) for a in acts)
+    assert _says(acts) == [MSG_WAIT_SPOT_DEFAULT.format(place="입구 오른쪽")]
+    assert logic.state == State.WAITING_RELEASE
+    logic.on_wait_speech_spoken(_says(acts)[0], t + 5.0)
+    acts = logic.on_tick(t + 5.1, NavStatus.NONE)
+    assert logic.state == State.MOVING_TO_WAIT_SPOT
+    assert [a.destination.id for a in acts if isinstance(a, Navigate)] == ["wait_spot:d1"]
+
+
+def test_returning_wait_without_spot_goes_to_the_entrance():
+    logic, t = returning()
+    acts = logic.on_voice_intent(intent("wait", wait_minutes=10), t, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_SPOT_CONFIRM.format(minutes=10, place="입구 앞")]
+    assert [a.destination.id for a in acts if isinstance(a, Navigate)] == ["wait_back:wc"]
+    assert logic.state == State.MOVING_BACK_TO_DEST
+    logic.on_tick(t + 20.0, NavStatus.SUCCEEDED)
+    assert logic.state == State.WAITING
+    assert logic.wait_place == "입구 앞"
+
+
+def test_braked_idle_wait_stops_the_return_ladder():
+    logic, t = idle_braked()
+    logic.on_voice_intent(intent("wait"), t, lookup, BOUNDS, True)
+    assert not logic.return_interrupted
+    logic.on_tick(t + 30.0, NavStatus.SUCCEEDED)        # 입구 앞 도착
+    assert logic.state == State.WAITING
+
+
+def test_after_home_wait_is_plain_idle_again():
+    """홈에 도착하면 직전 목적지를 잊는다 — 그 뒤의 "기다려"는 그냥 쉬는 중의 말이다."""
+    logic, t = returning()
+    logic.on_tick(t + 20.0, NavStatus.SUCCEEDED)        # 홈 도착
+    assert logic.state == State.IDLE
+    acts = logic.on_voice_intent(intent("wait"), t + 21.0, lookup, BOUNDS, True)
+    assert _says(acts) == ["지금은 안내 중이 아닙니다."]
+
+
+def test_late_answer_meaning_follows_the_question():
+    """대기형 질문("기다릴까요?")에 답이 없어 떠난 뒤: 네 = 대기, 아니요 = 그대로 홈."""
+    logic, t = returning_late()
+    acts = logic.on_voice_intent(intent("deny"), t, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_FINISH]
+    assert logic.state == State.RETURNING
+    # 한 번 답했으면 그다음 "네"는 늦은 답이 아니다.
+    assert logic.on_voice_intent(intent("affirm"), t + 1, lookup, BOUNDS, True) == []
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index 9fb6002..dfec339 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,19 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 9
-    "IDLE_BRAKED.finish": 9,
-    "IDLE_BRAKED.resume": 9,
-    "IDLE_BRAKED.wait": 9,
-    "IDLE_BRAKED_SPOT.finish": 9,
-    "IDLE_BRAKED_SPOT.resume": 9,
-    "IDLE_BRAKED_SPOT.wait": 9,
-    "RETURNING.finish": 9,
-    "RETURNING.wait": 9,
-    "RETURNING_LATE.finish": 9,
-    "RETURNING_LATE.no": 9,
-    "RETURNING_LATE.wait": 9,
-    "RETURNING_LATE.yes": 9,
     # Task 10
     "ASKING_WAIT_TIME.yes": 10,
     "CONFIRMING.navc": 10,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 10칸과 새 시험들이 실패한다(홈 도착 뒤 시험은 지금도 통과). 결과 줄: `19 failed, 945 passed, 1 skipped, 7 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/09-code.patch"
```

<details><summary>09-code.patch (198줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index ce13771..86cdb32 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1380,6 +1380,12 @@ class MissionLogic:
         self.door_side: str = ""
         # 도착 후 대화·대기의 목적지. _ask_arrival 이 active_destination 을 비우므로 따로 든다.
         self._arrived_destination: Optional[Destination] = None
+        # 마지막으로 사용자와 도착한 목적지(2026-10-08 결정 1). 홈으로 떠나도 남긴다 — 홈 가는
+        # 중의 "기다려"는 이 목적지 대기 장소로 간다. 홈 도착·새 안내·안내 뒤가 아닌 복귀·비상에서 지운다.
+        self._last_guided: Optional[Destination] = None
+        # 도착 질문에 답이 없어 떠났을 때 그 질문이 종료형이었나 — 늦게 온 "네·아니요"의 뜻이다.
+        # None 이면 늦은 답을 받을 질문이 없다(다 됐어·대기 만료로 떠났거나 이미 세웠다).
+        self._late_answer_finish: Optional[bool] = None
         # 지금 대기가 어디서인가: "spot"(대기 장소) / "destination"(막혀 목적지) / ""(제자리).
         self._wait_place: str = ""
         self._beacon_next_at: Optional[float] = None   # 다음 M3 시각
@@ -1510,18 +1516,37 @@ class MissionLogic:
             return None
         return handler(intent, now, lookup, bounds, nav_ready)
 
+    def _wait_at_last_guided(self, minutes: int, now: float) -> list:
+        """홈 가는 중의 "기다려" — 직전 목적지 대기 장소로 가서 기다린다(2026-10-08 결정 1).
+        대기 장소가 없으면 그 목적지 입구 앞으로, 직전 목적지가 없으면 그 자리에서 기다린다."""
+        last = self._last_guided
+        self._reset_arrival_dialog()
+        self._late_answer_finish = None
+        self._arrived_destination = last
+        if minutes is not None and minutes > 0:
+            return self._enter_waiting(min(minutes, WAIT_MINUTES_CAP), now, away=True)
+        return self._enter_waiting(WAIT_MINUTES_CAP, now, default_msg=True, away=True)
+
     @staticmethod
     def _ask(text: str) -> Say:
         """대답을 기다리는 말 — 노드가 듣기 창을 연다(expects_reply)."""
         return Say(text, priority="response", expects_reply=True)
 
     def _react_idle(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """안내 없음. 그냥 쉬는 중의 기다려·다 됐어 = 이유를 말한다(규칙 1). 홈 가다 세운 뒤
-        (복귀 재개 사다리)와 손잡이 잡기·온보딩 질문 중은 여기서 다루지 않는다."""
-        if (self._return_interrupted or self._grip_wait_since is not None
-                or self._dest_prompt_stage is not None):
+        """안내 없음. 홈 가다 "비카야"로 세운 뒤(복귀 재개 사다리)면 기다려 = 직전 목적지 대기
+        장소로(결정 1), 다 됐어·다시 가 = "안내를 종료합니다" 하고 바로 홈. 그냥 쉬는 중의
+        기다려·다 됐어 = 이유를 말한다(규칙 1). 손잡이 잡기·온보딩 질문 중은 다루지 않는다."""
+        kind = intent.intent
+        if self._grip_wait_since is not None or self._dest_prompt_stage is not None:
             return None
-        if intent.intent in ("wait", "finish"):
+        if self._return_interrupted:
+            if kind not in ("wait", "finish", "resume"):
+                return None
+            self._forget_interrupted_return()
+            if kind == "wait":
+                return self._wait_at_last_guided(intent.wait_minutes, now)
+            return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
+        if kind in ("wait", "finish"):
             return [Say(MSG_NOT_NAVIGATING, priority="response")]
         return None
 
@@ -1697,9 +1722,25 @@ class MissionLogic:
         return None
 
     def _react_returning(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """홈 복귀. 잠깐 = "비카야"처럼 세우고 "네?"(규칙 1, 옛 말은 "안내 중이 아닙니다"로
+        """홈 복귀. 기다려 = 세우고 직전 목적지 대기 장소로(결정 1). 다 됐어 = 그대로 홈 + 한마디.
+        답이 없어 떠난 뒤 늦게 온 네·아니요 = 그 질문의 뜻대로(대기형: 네 = 대기·아니요 = 홈,
+        종료형: 반대). 잠깐 = "비카야"처럼 세우고 "네?"(규칙 1, 옛 말은 "안내 중이 아닙니다"로
         못 세웠다). 관리자 홈 복귀의 잠깐은 지금처럼 일시정지다."""
-        if intent.intent == "pause" and not self._returning_home:
+        kind = intent.intent
+        if kind == "wait":
+            return (self.on_return_brake(now, quiet=True)
+                    + self._wait_at_last_guided(intent.wait_minutes, now))
+        if kind == "finish":
+            self._late_answer_finish = None
+            return [Say(MSG_FINISH, priority="response")]
+        if kind in ("affirm", "deny") and self._late_answer_finish is not None:
+            wants_wait = (kind == "affirm") != self._late_answer_finish
+            if wants_wait:
+                return (self.on_return_brake(now, quiet=True)
+                        + self._wait_at_last_guided(-1, now))
+            self._late_answer_finish = None
+            return [Say(MSG_FINISH, priority="response")]
+        if kind == "pause" and not self._returning_home:
             return self.on_return_brake(now) + [self._ask(MSG_WAKE_GREETING)]
         return None
 
@@ -1906,6 +1947,9 @@ class MissionLogic:
         # 사용자는 이미 응답한 것이다). 안 지우면 이번 안내를 마치고 한참 뒤
         # 낡은 복귀 사다리가 갑자기 홈으로 떠난다.
         self._forget_interrupted_return()
+        # 새 안내다 — 지난 안내의 목적지·늦은 답은 넘겨받지 않는다(결정 1).
+        self._last_guided = None
+        self._late_answer_finish = None
         return [
             SetNavSpeedLimit(NO_SPEED_LIMIT),
             Say(say_destination(MSG_START, dest.name)),
@@ -2895,6 +2939,7 @@ class MissionLogic:
         # 목적지 없이 다시 묻는 자리(재질문)에서는 앞서 든 값을 그대로 둔다.
         if dest is not None:
             self._arrived_destination = dest
+            self._last_guided = dest
         self.active_destination = None
         self._asking_is_finish = is_finish
         self._asking_time_after_yes = ask_time
@@ -3222,11 +3267,12 @@ class MissionLogic:
         return self._arrival_no_answer(now)
 
     def _enter_waiting(self, minutes: int, now: float,
-                       default_msg: bool = False) -> list:
+                       default_msg: bool = False, away: bool = False) -> list:
         """대기 확정 + 멘트. 사람접근은 대기 상태값으로 자연히 꺼진다.
 
         대기 장소가 있는 목적지면 M2/M2′ 를 말하고 손 놓기를 기다린다
-        (WAITING_RELEASE). 없으면 지금처럼 그 자리에서 기다린다(WAITING).
+        (WAITING_RELEASE). 없으면 지금처럼 그 자리에서 기다린다(WAITING). away(목적지를
+        떠나 있음, 2026-10-08 결정 1)면 대기 장소가 없는 목적지는 그 입구 앞으로 돌아간다.
         대기 시간은 어느 쪽이든 이 순간(멘트를 말한 순간)부터 흐른다 — 말한
         "N분 동안"이 맞게(2026-10-07).
         """
@@ -3237,6 +3283,20 @@ class MissionLogic:
         dest = self._arrived_destination
         spot = dest.wait_spot if dest is not None else None
         place = WAIT_PLACE_PHRASES.get(spot.side, "") if spot is not None else ""
+        if not place and away and dest is not None:
+            # 목적지를 떠나 있다(홈 가는 중 "기다려", 결정 1) — 대기 장소가 없는 목적지면 그
+            # 입구 앞으로 돌아가 기다린다. 장소 말은 대기 장소가 막혔을 때(M6)와 같다.
+            msg = (MSG_WAIT_SPOT_DEFAULT.format(place=WAIT_PLACE_AT_DESTINATION) if default_msg
+                   else MSG_WAIT_SPOT_CONFIRM.format(minutes=minutes,
+                                                     place=WAIT_PLACE_AT_DESTINATION))
+            back = wait_back_destination(dest)
+            self.state = State.MOVING_BACK_TO_DEST
+            self.active_destination = back
+            self.handle_active = False
+            self._wait_place = "destination"
+            self._beacon_next_at = now + WAIT_BEACON_INTERVAL_SEC
+            return [Say(msg, priority="response"), SetNavSpeedLimit(NO_SPEED_LIMIT),
+                    Navigate(back, tree=NAV_TREE_WAIT)]
         if not place:
             self.state = State.WAITING
             self._wait_place = ""
@@ -3499,6 +3559,8 @@ class MissionLogic:
             return []
         # on_wake_doa 가 이 시각을 봐 이 소비를 새 호출로 오인하지 않는다.
         self._wake_consumed_at = now
+        # 세웠다 — 그 뒤의 "네·아니요"는 늦은 답이 아니라 지금 대화다(결정 1).
+        self._late_answer_finish = None
         cancel_dest = self.active_destination
         self.active_destination = None
         actions: list = [SetNavSpeedLimit(NO_SPEED_LIMIT)]
@@ -3873,6 +3935,10 @@ class MissionLogic:
             if (self._leaving_deadline is not None
                     and now >= self._leaving_deadline
                     and not self._ear_holds(now)):
+                # 답이 없어 떠난다 — 홈 가는 중 늦게 온 "네·아니요"를 이 질문의 뜻으로 받는다
+                # (2026-10-08 결정 1). 물어 둔 질문이 없었으면 받을 뜻도 없다.
+                self._late_answer_finish = (
+                    self._asking_is_finish if self._asking_question else None)
                 self._reset_arrival_dialog()
                 # 복귀 멘트는 2026-09-01 감량 — 직전 떠나기 예고가 이미 말했다.
                 actions.extend(self._go_home(now))
@@ -4091,9 +4157,14 @@ class MissionLogic:
         track_id 는 아직 지우지 않는다. 재접근 억제는 복귀가 끝난 시점부터
         세야 하므로 _finish_returning 까지 들고 간다(설계 4절).
         """
-        # 목적지를 떠난다 — 그 목적지의 대기 장소는 더 쓰지 않는다(2026-10-07). 복귀 중
-        # 불러 세워 "기다려 줘"가 와도 옛 목적지 대기 장소로 가지 않고 그 자리에서 기다린다.
+        # 목적지를 떠난다 — 도착 대화의 목적지는 비운다. 안내를 마치고 떠나는 복귀라면
+        # _last_guided 가 그 목적지를 기억한다: 홈 가는 중 "기다려"는 그 대기 장소로 간다
+        # (2026-10-08 사용자 결정 1 — 10-07 의 '그 자리에서 기다린다'를 바꿨다). 접근 뒤·
+        # 관리자 복귀에는 돌아갈 안내 목적지가 없다.
         self._arrived_destination = None
+        if not dialog_finish:
+            self._last_guided = None
+            self._late_answer_finish = None
         # 입구 방향(M1 기준)도 떠나면 낡은 말이다 — LLM 메모에 옛 목적지 방향이 남지 않게.
         self.door_side = ""
         # auto_return_home 게이트는 접근 뒤 복귀에만 걸린다 — 꺼져 있으면 그
@@ -4131,6 +4202,9 @@ class MissionLogic:
         """
         track_id = self.approach_track_id
         was_home = self._returning_home
+        # 홈에 왔다 — 홈 가는 중의 "기다려"·늦은 답은 여기서 끝이다(결정 1).
+        self._last_guided = None
+        self._late_answer_finish = None
         self._to_idle()
         if not was_home:
             self._suppress_track(track_id, now)
@@ -4167,6 +4241,8 @@ class MissionLogic:
         self._cancel_confirm_deadline = None
         self._confirming_dest_id = None
         self._confirm_deadline = None
+        self._last_guided = None
+        self._late_answer_finish = None
         self._estop_entered_at = now
         self._estop_clear_since = None
         self._announced_milestones = set()
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 961 passed, 1 skipped, 7 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "feat(mission): 홈 가는 중 기다려는 직전 목적지 대기 장소로 — 사용자 결정 1, 늦은 네·아니요는 질문의 뜻대로" -m "$VICA_TRAILER"
```


### Task 10: 결정 2·4 — 시간 질문의 "네"는 다시 묻고, 확인 질문 중 다른 목적지는 "네, XX로…"

사용자 결정 2(덧붙임: 다시 물어도 "네"면 기본 30분)와 결정 4(사용자 문구 "네, XX로 안내해드릴까요?",
새 상수 `MSG_CONFIRM_SWITCH`). 확인 질문 중 다른 목적지를 확정하면 09-01의 '말없이 접기' 대신 그 목적지로
다시 묻는다 — 갈 수 없는 곳이면 이유를 말하고 묻던 질문은 그대로 둔다.

09-01 동작을 못 박은 기존 시험 3개를 새 결정으로 고친다: `test_destination_change.py`
`test_stale_confirmed_other_destination_resumes_with_message` → `test_other_confirmed_destination_is_asked_again`,
`test_mission_logic.py` `test_stale_confirm_different_dest_rejected` → `…_asks_again`,
`TestStaleConfirmListens.test_stale_confirm_retry_prompt_expects_a_reply`(뜻은 같고 기대값만).

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 확인 질문 | 목적지 확정 | (말 없음) → 안내 없음 | “네, 엘리베이터로 안내해드릴까요?” → 확인 질문 |
| 주행 중 바꾸기 질문 | 목적지 확정 | “409호로 다시 출발합니다.” → 안내 주행 | “네, 엘리베이터로 안내해드릴까요?” → 확인 질문 |
| 시간 질문 | 네 | “잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.” → 시간 질문 | “몇 분쯤 걸리실까요?” → 시간 질문 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_destination_change.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 상수 `MSG_CONFIRM_SWITCH = "네, {prompt}"`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/10-test.patch"
```

<details><summary>10-test.patch (158줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_destination_change.py b/src/vica_mission_manager/test/test_destination_change.py
index a320363..ec0e035 100644
--- a/src/vica_mission_manager/test/test_destination_change.py
+++ b/src/vica_mission_manager/test/test_destination_change.py
@@ -145,11 +145,14 @@ class TestAnswers:
         assert logic.active_destination == ROOM
         assert _navs(actions)[0].destination == ROOM
 
-    def test_stale_confirmed_other_destination_resumes_with_message(self):
+    def test_other_confirmed_destination_is_asked_again(self):
+        """바꾸기 질문 중 또 다른 목적지를 확정하면 그 목적지로 다시 묻는다 — 바꾸기 질문은
+        그대로다(2026-10-08 결정 4, 옛 09-01 동작은 말없이 원래 목적지로 다시 출발)."""
         logic, _ = asked_change()
         actions = logic.on_intent(_intent(CAFE.id), CAFE, BOUNDS, True, 2.0)
-        assert logic.state == State.NAVIGATING and logic.active_destination == ROOM
-        assert _say(actions) == ["409호로 다시 출발합니다."]
+        assert logic.state == State.CONFIRMING and logic.confirming_dest_id == CAFE.id
+        assert _say(actions) == ["네, 식당으로 모실까요?"]   # CAFE 의 확인 문장 앞에 "네, "
+        assert logic._change_from == ROOM
 
     def test_gate_failure_on_yes_rejects_then_resumes(self):
         lost = Destination(id="lost", name="창고", pose=Pose2D(x=1, y=1, yaw_deg=0, frame_id="map"),
diff --git a/src/vica_mission_manager/test/test_mission_logic.py b/src/vica_mission_manager/test/test_mission_logic.py
index d65dbec..585ea37 100644
--- a/src/vica_mission_manager/test/test_mission_logic.py
+++ b/src/vica_mission_manager/test/test_mission_logic.py
@@ -278,7 +278,9 @@ class TestTransitions:
         assert logic.state != State.NAVIGATING
         assert not any(isinstance(a, Navigate) for a in actions)
 
-    def test_stale_confirm_different_dest_rejected(self):
+    def test_stale_confirm_different_dest_asks_again(self):
+        """확인 질문 중 다른 목적지를 확정하면 그 목적지로 다시 묻는다(2026-10-08 결정 4).
+        옛 09-01 동작은 멘트 없이 접기였다 — 출발하지 않는 것은 같다."""
         logic = MissionLogic()
         logic.on_intent(
             make_intent(need_confirm=True, matched_destination_id="restroom"),
@@ -286,9 +288,9 @@ class TestTransitions:
         )
         actions = logic.on_intent(make_intent(matched_destination_id="room_407"),
                                   make_dest(), BOUNDS, True, 5.0)
-        assert logic.state == State.IDLE
-        # 9/1 감량: 멘트 없이 접는다 — 출발만 안 하면 된다.
-        assert not any(isinstance(a, Say) for a in actions)
+        assert logic.state == State.CONFIRMING and logic.confirming_dest_id == "room_407"
+        assert [a.text for a in actions if isinstance(a, Say)] == [
+            "네, 윤지영 교수님 사무실로 안내해드릴까요?"]
         assert not any(isinstance(a, Navigate) for a in actions)
 
     def test_navigating_confirmed_request_stops_and_asks(self):
@@ -1346,19 +1348,19 @@ class TestApproachSafety:
 
 class TestStaleConfirmListens:
     def test_stale_confirm_retry_prompt_expects_a_reply(self):
-        """"다시 말씀해 주세요"는 질문이다 — expects_reply 없이는 말해 놓고
-        안 듣는다 (2026-08-28 실기: 사용자가 "비카야"를 다시 불러야 했다)."""
+        """엇갈린 확정에 다시 묻는 말은 질문이다 — expects_reply 없이는 말해 놓고
+        안 듣는다 (2026-08-28 실기: 사용자가 "비카야"를 다시 불러야 했다).
+        2026-10-08 결정 4로 그 목적지를 "네, …로 안내해드릴까요?"로 다시 묻는다."""
         logic = MissionLogic()
         logic.on_intent(make_intent(need_confirm=True), make_dest(), BOUNDS,
                         True, 0.0)
         assert logic.state == State.CONFIRMING
         actions = logic.on_intent(
-            make_intent(matched_destination_id="다른_목적지"), make_dest(),
-            BOUNDS, True, 1.0)
-        # 2026-09-01 감량: 엇갈린 confirm 은 멘트 없이 접는다 — 침묵이면
-        # 사용자가 다시 말하고, 그 요청이 새 확인 흐름을 연다.
-        assert not any(isinstance(a, Say) for a in actions)
-        assert logic.state == State.IDLE
+            make_intent(matched_destination_id="다른_목적지"),
+            make_dest(id="다른_목적지"), BOUNDS, True, 1.0)
+        says = [a for a in actions if isinstance(a, Say)]
+        assert len(says) == 1 and says[0].expects_reply
+        assert logic.state == State.CONFIRMING
 class TestApproachVoiceHooks:
     """계획 문서(voice docs/approach-voice-flow.md)의 남은 두 조각.
 
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index ec26dcd..dbc3306 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -2,16 +2,19 @@
 
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
-from reaction_states import (BOUNDS, ELEV, SPOT_DEST, asking, asking_wait_time, idle_braked,
-                             intent, lookup, navigating, returning, returning_late, waiting,
-                             waiting_asked, waiting_release)
+from reaction_states import (BOUNDS, ELEV, ROOM, SPOT_DEST, asking, asking_wait_time,
+                             confirming, idle_braked, intent, lookup, navigating, returning,
+                             returning_late, waiting, waiting_asked, waiting_release)
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
     MSG_ASK_ENTRANCE,
+    MSG_ASK_WAIT_TIME,
+    MSG_CONFIRM_SWITCH,
     MSG_CANCEL_KEPT,
     MSG_CANCEL_CONFIRM,
     MSG_CANCELED,
     MSG_FINISH,
+    MSG_PRIVATE_DEST,
     MSG_START,
     MSG_WAIT_DEFAULT,
     MSG_WAIT_FINISH_ASK,
@@ -226,3 +229,37 @@ def test_late_answer_meaning_follows_the_question():
     assert logic.state == State.RETURNING
     # 한 번 답했으면 그다음 "네"는 늦은 답이 아니다.
     assert logic.on_voice_intent(intent("affirm"), t + 1, lookup, BOUNDS, True) == []
+
+
+# ---- Task 10: 결정 2·4 ----------------------------------------------------------
+def test_wait_time_yes_twice_waits_30_minutes():
+    logic, t = asking_wait_time()
+    assert _says(logic.on_voice_intent(intent("affirm"), t, lookup, BOUNDS, True)) == [
+        MSG_ASK_WAIT_TIME]
+    acts = logic.on_voice_intent(intent("affirm"), t + 3, lookup, BOUNDS, True)
+    assert _says(acts) == [MSG_WAIT_DEFAULT]
+    assert logic.state == State.WAITING
+
+
+def test_switch_question_is_the_users_sentence():
+    assert MSG_CONFIRM_SWITCH.format(prompt="엘리베이터로 안내해드릴까요?") == (
+        "네, 엘리베이터로 안내해드릴까요?")
+
+
+def test_switch_then_yes_goes_to_the_new_place():
+    logic, t = confirming()
+    logic.on_voice_intent(intent(matched_destination_id=ELEV.id), t, lookup, BOUNDS, True)
+    assert logic.confirming_dest_id == ELEV.id
+    acts = logic.on_voice_intent(intent("affirm"), t + 2, lookup, BOUNDS, True)
+    assert _says(acts) == [say_destination(MSG_START, "엘리베이터")]
+    assert logic.state == State.NAVIGATING
+
+
+def test_switch_to_a_closed_place_keeps_the_question():
+    closed = ROOM.__class__(**{**ROOM.__dict__, "id": "vip", "name": "원장실",
+                               "authorization": "private"})
+    logic, t = confirming()
+    acts = logic.on_voice_intent(intent(matched_destination_id="vip"), t,
+                                 lambda i: closed if i == "vip" else lookup(i), BOUNDS, True)
+    assert _says(acts) == [MSG_PRIVATE_DEST]
+    assert logic.state == State.CONFIRMING and logic.confirming_dest_id == "wc"
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index dfec339..d8702b4 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,10 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 10
-    "ASKING_WAIT_TIME.yes": 10,
-    "CONFIRMING.navc": 10,
-    "CONFIRMING_CHANGE.navc": 10,
     # Task 11
     "AWAITING_USER.navc": 11,
     "AWAITING_USER.navp": 11,
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `test/test_reaction_rules.py` 수집 오류 — `ImportError: cannot import name 'MSG_CONFIRM_SWITCH'`. 결과 줄: `5c/scratchpad/proto/wt/tmpkwohgbjb/r/vica_mission_manager/mission_logic.py)
=========================== short test summary info ============================
ERROR test/test_reaction_rules.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 skipped, 1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/10-code.patch"
```

<details><summary>10-code.patch (54줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index 86cdb32..b3dac8c 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -415,6 +415,9 @@ MSG_ESTOP_WAKE = "지금은 비상 멈춤 상태입니다."
 # 확인 질문 문구가 빈 목적지를 미션이 직접 물을 때(주행 중 바로 온 확정 요청). 음성
 # destination_loader._fill_defaults 의 기본 확인 문구와 같은 글자 — 그쪽이 미리 합성해 둔다.
 MSG_CONFIRM_PROMPT_FALLBACK = "{name}{josa} 안내해드릴까요?"
+# 확인 질문 중 다른 목적지를 확정하면 새 목적지로 다시 묻는다(2026-10-08 사용자 결정 4, 사용자
+# 문구). {prompt} 는 새 목적지의 확인 질문이다 — 음성 쪽이 목적지마다 미리 합성한다.
+MSG_CONFIRM_SWITCH = "네, {prompt}"
 
 MSG_DISTANCE_REMAINING = "목적지까지 약 {meters}미터 남았습니다."
 MSG_CANCELED = "안내를 취소했습니다."
@@ -1627,6 +1630,15 @@ class MissionLogic:
                 self._reset_arrival_dialog()
                 return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
             return self._arrival_no_answer(now)
+        if self.state == State.ASKING_WAIT_TIME and kind == "affirm":
+            # "몇 분쯤 걸리실까요?"에 "네"만 — 같은 질문을 한 번 다시 묻는다(결정 2). 다시 물은
+            # 뒤에도 "네"면 기다려 달라는 뜻이 분명하니 기본 30분을 기다린다.
+            if not self._arrival_retried:
+                self._arrival_retried = True
+                self._response_deadline = None
+                self._asking_entered_at = now
+                return [self._ask(MSG_ASK_WAIT_TIME)]
+            return self._enter_waiting(WAIT_MINUTES_CAP, now, default_msg=True)
         if self.state == State.ASKING_WAIT_TIME and kind == "deny":
             # "몇 분쯤 걸리실까요?"에 "아니(기다리지 마)" — 끝낼지 한 번 확인한다.
             return self._ask_end_confirm(now)
@@ -1894,11 +1906,18 @@ class MissionLogic:
             and self._confirming_dest_id
             and intent.matched_destination_id != self._confirming_dest_id
         ):
-            # 오래된/엇갈린 confirm 방어 (request_id 없는 v1 의 임시 방어).
-            # 멘트 없이 접는다(2026-09-01 감량) — 침묵이면 사용자가 다시
-            # 말하고, 그 요청이 새 확인 흐름을 연다. 주행 중 바꾸기 질문이었으면
-            # 원래 목적지로 다시 출발한다 — 움직이므로 그때는 알린다.
-            return self._fold_confirming(now)
+            # 확인 질문 중 다른 목적지를 확정했다 — 새 목적지로 다시 묻는다(2026-10-08 사용자
+            # 결정 4, "네, XX로 안내해드릴까요?"). 09-01 의 '멘트 없이 접기'는 규칙 1(꼭 한마디)
+            # 로 바꿨다. 갈 수 없는 곳이면 이유를 말하고 묻던 질문은 그대로 둔다.
+            reason = check_gate(intent, dest, bounds, self.estop_active, nav_ready)
+            if reason != GateReason.OK:
+                msg = _REJECT_MESSAGES.get(reason)
+                return [Say(msg, priority="response")] if msg else []
+            assert dest is not None  # check_gate 가 보장
+            self._confirming_dest_id = dest.id
+            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._confirm_prompt = self._confirm_prompt_for(dest)
+            return [self._ask(MSG_CONFIRM_SWITCH.format(prompt=self._confirm_prompt))]
 
         reason = check_gate(intent, dest, bounds, self.estop_active, nav_ready)
         if reason != GateReason.OK:
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 968 passed, 1 skipped, 4 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_destination_change.py src/vica_mission_manager/test/test_mission_logic.py src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "feat(mission): 시간 질문의 네는 다시 묻고, 확인 질문 중 다른 목적지는 '네, XX로…'로 — 사용자 결정 2·4" -m "$VICA_TRAILER"
```


### Task 11: 접근 질문에 목적지로 답하면 수락하고, 돌아선 뒤 그 목적지를 묻는다

규칙 1. "안내를 받으시겠어요?"에 "응, 화장실 가고 싶어" = 수락("네, 잠시만 기다려주세요…" + 회전)하고
목적지를 `_approach_dest`로 기억한다. 손잡이 안내 뒤 온보딩 대신 그 목적지 확인 질문을 한다. 돌아서는 중에
말한 목적지도 기억한다(그때는 말을 얹지 않는다). 갈 수 없는 곳이면 기억하지 않고 평소 온보딩. 음성 쪽 짝은
작업 13(지시문)·14(LLM 확인 질문 지우기) — 함께 들어가야 두 목소리가 안 난다.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 접근 질문 | 목적지 제안 | (말 없음) → 접근 질문 | “네, 잠시만 기다려주세요. 로봇이 회전하니 주의하세요.” → 돌아서기 |
| 접근 질문 | 목적지 확정 | “지금은 다른 응대 중입니다. 잠시 후 다시 말씀해 주세요.” → 접근 질문 | “네, 잠시만 기다려주세요. 로봇이 회전하니 주의하세요.” → 돌아서기 |
| 돌아서기 | 목적지 확정 | “지금은 다른 응대 중입니다. 잠시 후 다시 말씀해 주세요.” → 돌아서기 | (말 없음) → 돌아서기 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 필드 `_approach_dest: Optional[Destination]`; `_approach_destination(intent, lookup, bounds, nav_ready) -> Optional[Destination]`; 처리기 `_react_turning`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/11-test.patch"
```

<details><summary>11-test.patch (75줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index dbc3306..26ce239 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -3,12 +3,15 @@
 칸 하나의 첫 반응은 test_reaction_table.py 가 못 박는다. 여기는 그 뒤에 이어지는 일을 본다.
 """
 from reaction_states import (BOUNDS, ELEV, ROOM, SPOT_DEST, asking, asking_wait_time,
-                             confirming, idle_braked, intent, lookup, navigating, returning,
-                             returning_late, waiting, waiting_asked, waiting_release)
+                             awaiting_user, confirming, idle_braked, intent, lookup, navigating,
+                             returning, returning_late, turning, waiting, waiting_asked,
+                             waiting_release)
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
+    MSG_APPROACH_ONBOARDING,
     MSG_ASK_ENTRANCE,
     MSG_ASK_WAIT_TIME,
+    MSG_CONFIRM_PROMPT_FALLBACK,
     MSG_CONFIRM_SWITCH,
     MSG_CANCEL_KEPT,
     MSG_CANCEL_CONFIRM,
@@ -263,3 +266,37 @@ def test_switch_to_a_closed_place_keeps_the_question():
                                  lambda i: closed if i == "vip" else lookup(i), BOUNDS, True)
     assert _says(acts) == [MSG_PRIVATE_DEST]
     assert logic.state == State.CONFIRMING and logic.confirming_dest_id == "wc"
+
+
+# ---- Task 11: 접근 질문에 목적지로 답하기 -----------------------------------------
+def _after_turn(logic, t):
+    """회전이 끝났다 — 손잡이 안내 뒤(시험 로봇은 터치 센서가 없어 바로) 다음 질문이 나온다."""
+    return _says(logic.on_tick(t, NavStatus.SUCCEEDED))
+
+
+def test_destination_answer_is_accepted_and_asked_after_the_turn():
+    logic, t = awaiting_user()
+    logic.on_voice_intent(intent(matched_destination_id=ELEV.id, need_confirm=True), t,
+                          lookup, BOUNDS, True)
+    assert logic.state == State.TURNING
+    says = _after_turn(logic, t + 4.0)
+    assert says[-1] == say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "엘리베이터")
+    assert logic.state == State.CONFIRMING and logic.confirming_dest_id == ELEV.id
+    acts = logic.on_voice_intent(intent("affirm"), t + 6.0, lookup, BOUNDS, True)
+    assert _says(acts) == [say_destination(MSG_START, "엘리베이터")]
+
+
+def test_destination_said_while_turning_is_remembered():
+    logic, t = turning()
+    assert logic.on_voice_intent(intent(matched_destination_id=ELEV.id), t, lookup,
+                                 BOUNDS, True) == []
+    says = _after_turn(logic, t + 3.0)
+    assert says[-1] == say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "엘리베이터")
+
+
+def test_unknown_destination_falls_back_to_onboarding():
+    logic, t = awaiting_user()
+    logic.on_voice_intent(intent(matched_destination_id="nowhere", need_confirm=True), t,
+                          lookup, BOUNDS, True)
+    assert logic.state == State.TURNING
+    assert _after_turn(logic, t + 4.0)[-1] == MSG_APPROACH_ONBOARDING
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index d8702b4..f35f18d 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,10 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 11
-    "AWAITING_USER.navc": 11,
-    "AWAITING_USER.navp": 11,
-    "TURNING.navc": 11,
     # Task 12
     "WAITING_ASKED.yes": 12,
 }
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 에서 지운 3칸과 새 시험 3개가 실패한다. 결과 줄: `9 failed, 968 passed, 1 skipped, 1 xfailed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/11-code.patch"
```

<details><summary>11-code.patch (104줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index b3dac8c..baaf00b 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -1408,6 +1408,9 @@ class MissionLogic:
         # 원래 가던 목적지를 여기 든다. 확정되면 새 목적지로, 거절·무응답·호출이면 이
         # 목적지로 다시 출발한다(_fold_confirming). 대기 보류(_wait_hold)와 같은 틀이다.
         self._change_from: Optional[Destination] = None
+        # 접근 질문·돌아서기 중에 사용자가 말한 목적지(2026-10-08 반응표). 손잡이를 내준 뒤
+        # 온보딩 대신 이 목적지로 확인 질문을 한다. 그때 쓰고 비운다.
+        self._approach_dest: Optional[Destination] = None
         # 지금 확인 질문의 문장(2026-10-08 반응표). "다시 가자"·다시 묻기에서 같은 질문을 한다.
         self._confirm_prompt = ""
         # 지금 안내 주행의 행동 트리 종류. 재시도·재개가 같은 트리를 쓰게 한다.
@@ -1513,6 +1516,7 @@ class MissionLogic:
             State.WAITING_RELEASE: self._react_waiting,
             State.WAITING: self._react_waiting,
             State.AWAITING_USER: self._react_awaiting_user,
+            State.TURNING: self._react_turning,
             State.RETURNING: self._react_returning,
         }.get(self.state)
         if handler is None:
@@ -1724,8 +1728,12 @@ class MissionLogic:
         return [Say(msg, priority="response")]
 
     def _react_awaiting_user(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
-        """접근 질문. 취소 = 아니요(물러난다). 잠깐·다시 가자 = "네?" 하고 질문 유지, 답 시계를
-        지금부터 다시 센다."""
+        """접근 질문. 목적지로 답하면("응, 화장실 가고 싶어") 수락으로 받고 그 목적지를 기억한다
+        — 돌아서 손잡이를 내준 뒤 확인 질문으로 묻는다(규칙 1, 옛 동작은 버림·"다른 응대 중").
+        취소 = 아니요(물러난다). 잠깐·다시 가자 = "네?" 하고 질문 유지, 답 시계를 다시 센다."""
+        if intent.intent == "navigate":
+            self._approach_dest = self._approach_destination(intent, lookup, bounds, nav_ready)
+            return self.on_approach_answer(True, now)
         if intent.intent == "cancel":
             return self.on_approach_answer(False, now)
         if intent.intent in ("pause", "resume"):
@@ -1733,6 +1741,25 @@ class MissionLogic:
             return [self._ask(MSG_WAKE_GREETING)]
         return None
 
+    def _react_turning(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
+        """돌아서는 중에 말한 목적지 — 기억했다가 손잡이를 내준 뒤 확인 질문으로 묻는다.
+        도는 동안은 말을 얹지 않는다(옛 동작은 확정에 "지금은 다른 응대 중입니다")."""
+        if intent.intent != "navigate":
+            return None
+        dest = self._approach_destination(intent, lookup, bounds, nav_ready)
+        if dest is not None:
+            self._approach_dest = dest
+        return []
+
+    def _approach_destination(self, intent, lookup, bounds, nav_ready) -> Optional[Destination]:
+        """접근 대화 중 받은 목적지 — 갈 수 있는 곳만 기억한다. 못 가는 곳이면 None 이고,
+        손잡이를 내준 뒤 평소 온보딩("어디로 가고 싶으신가요?")을 한다."""
+        dest = lookup(intent.matched_destination_id)
+        confirmed = replace(intent, need_confirm=False)
+        if check_gate(confirmed, dest, bounds, self.estop_active, nav_ready) != GateReason.OK:
+            return None
+        return dest
+
     def _react_returning(self, intent, now, lookup, bounds, nav_ready) -> Optional[list]:
         """홈 복귀. 기다려 = 세우고 직전 목적지 대기 장소로(결정 1). 다 됐어 = 그대로 홈 + 한마디.
         답이 없어 떠난 뒤 늦게 온 네·아니요 = 그 질문의 뜻대로(대기형: 네 = 대기·아니요 = 홈,
@@ -2526,6 +2553,7 @@ class MissionLogic:
             return [Navigate(destination)], GateReason.OK
 
         self.state = State.APPROACHING
+        self._approach_dest = None
         self.active_destination = destination
         self.approach_track_id = request.track_id
         self.approach_goal_pose = request.goal
@@ -2642,6 +2670,16 @@ class MissionLogic:
         actions: list = []
         if engaged:
             actions.append(Haptic(HAPTIC_PATTERN_GRIP_ACK))
+        approach_dest = self._approach_dest
+        self._approach_dest = None
+        if approach_dest is not None:
+            # 접근 질문에 목적지로 답했다 — 온보딩 대신 그 목적지를 확인한다(2026-10-08 반응표).
+            self.state = State.CONFIRMING
+            self._confirming_dest_id = approach_dest.id
+            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._confirm_prompt = self._confirm_prompt_for(approach_dest)
+            actions.append(self._ask(self._confirm_prompt))
+            return actions
         # 온보딩 질문을 던지는 자리 — 빈손 되묻기 사다리를 켠다.
         self._arm_dest_prompt(now)
         actions.append(Say(MSG_APPROACH_ONBOARDING, priority="response",
@@ -3932,6 +3970,7 @@ class MissionLogic:
             elif (self._turn_deadline is not None
                   and now >= self._turn_deadline):
                 # spin 이 시작조차 안 됐다(노드 결함 등). 시계로 탈출한다.
+                self._approach_dest = None
                 self._to_idle()
 
         elif self.state == State.AWAITING_USER:
@@ -4262,6 +4301,7 @@ class MissionLogic:
         self._confirm_deadline = None
         self._last_guided = None
         self._late_answer_finish = None
+        self._approach_dest = None
         self._estop_entered_at = now
         self._estop_clear_since = None
         self._announced_milestones = set()
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 974 passed, 1 skipped, 1 xfailed` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "feat(mission): 접근 질문에 목적지로 답하면 수락하고 돌아선 뒤 그 목적지를 묻는다(반응표 규칙 1)" -m "$VICA_TRAILER"
```


### Task 12: 다시 묻기 — 질문마다 한 번

사용자 제안(10-08). 확인 질문 = 15초 조용하면 한 번 다시, 30초면 지금처럼 접음. 못 알아들은 답(unknown)이면
바로 한 번 다시. 취소 확인 = 15초에 한 번 다시, 시간이 다 되면 지금처럼 계속(이제 일시정지·바꾸기 질문 중에
물은 것도 시간이 끝난다 — 예전엔 안내 주행 중에만 시계를 봤다). 도착·시간 질문의 못 알아들은 답 = "잘 듣지
못했습니다…" 대신 그 질문 자체를 다시(기회는 대답 없음과 합쳐 한 번). 대기 중 "어디로 모실까요?"·"안내가
필요 없으신가요?" = 15초에 한 번 다시, 그래도 없으면 계속 대기(뒤의 것은 "안내를 계속하겠습니다.").

LLM이 되묻는 중(clarify, "어느 화장실이요?")에는 미션이 끼어들지 않는다 — 도착 질문에서 clarify 는 이제
"질문"처럼 다룬다(예전엔 다시 묻기 사다리로 가서 두 목소리가 났다). 다시 묻기가 틱이 늦어 마감과 겹치면 먼저
묻고 답할 시간(15초)을 남긴다. 다시 묻는 틱에는 M3를 얹지 않는다.

옛 동작을 못 박은 기존 시험 7개를 고친다: `test_arrival_dialog.py`의 `test_unknown_retries_once_then_leaves`·
`test_affirm_reasks`·`test_deny_reasks`, `test_destination_change.py`의 `test_silence_resumes_original`,
`test_mission_logic.py`의 `test_confirm_timeout_30s`·`TestVoiceCancelConfirm.test_timeout_keeps_navigating`,
`test_wait_spot.py`의 `test_confirm_timeout_and_wake_return_to_waiting`.

**바뀌는 칸**(반응표 시험 `PENDING`의 이 작업 묶음):

| 상태 | 요청 | 지금 | 바뀐 뒤 |
| --- | --- | --- | --- |
| 대기 중 '어디로 모실까요?' 뒤 | 네 | (말 없음) → 대기 중 | “네, 어디로 모실까요?” → 대기 중 |

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_arrival_dialog.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_destination_change.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_table.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_wait_spot.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`

**Interfaces:**
- Produces: 상수 `QUESTION_REASK_SEC = 15.0`; `_arm_confirm(now)`, `_cancel_confirm_tick(now) -> list`, `_wait_question_tick(now) -> list`
- Produces: 필드 `_confirm_reask_at`, `_confirm_reasked`, `_cancel_reask_at`, `_cancel_reasked`, `_wait_finish_reasked`, `_wait_need_reasked`
- 음성 짝: 작업 14(미션이 질문 중이면 LLM 의 unknown 대답을 지운다) — 함께 들어가야 목소리가 하나다

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/12-test.patch"
```

<details><summary>12-test.patch (192줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_arrival_dialog.py b/src/vica_mission_manager/test/test_arrival_dialog.py
index 60a707d..408ce6d 100644
--- a/src/vica_mission_manager/test/test_arrival_dialog.py
+++ b/src/vica_mission_manager/test/test_arrival_dialog.py
@@ -141,9 +141,11 @@ class TestFinishAndNext:
 
 class TestNoAnswerLadder:
     def test_unknown_retries_once_then_leaves(self):
+        """못 알아들은 답에는 질문 자체를 한 번 더 묻는다(2026-10-08 다시 묻기 — 옛 문장은
+        "잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해 주세요.")."""
         logic = arrive("restroom")
         acts = logic.on_arrival_answer(_intent("unknown"), 3.0)
-        assert MSG_ARRIVAL_RETRY in _say(acts)
+        assert _say(acts) == [MSG_ASK_RESTROOM]
         assert logic.state == State.ASKING_NEXT       # 아직 안 떠남
         logic.on_arrival_question_spoken(4.0)
         acts2 = logic.on_arrival_answer(_intent("unknown"), 5.0)
@@ -495,13 +497,15 @@ class TestAskWaitTimeRejectsYesNo:
         logic = self._to_wait_time()
         acts = logic.on_arrival_answer(_intent("affirm"), 5.0)
         assert logic.state == State.ASKING_WAIT_TIME       # 홈에 안 감
-        assert MSG_ARRIVAL_RETRY in _say(acts)
+        assert _say(acts) == [MSG_ASK_WAIT_TIME]           # 질문 자체를 다시(2026-10-08)
 
     def test_deny_reasks(self):
+        """이 경로(on_arrival_answer 직접)는 옛 그물이다 — 음성 요청은 on_voice_intent 가
+        "여기까지 안내를 마칠까요?"로 받는다(test_reaction_table)."""
         logic = self._to_wait_time()
         acts = logic.on_arrival_answer(_intent("deny"), 5.0)
         assert logic.state == State.ASKING_WAIT_TIME       # 30분 대기도 안 함
-        assert MSG_ARRIVAL_RETRY in _say(acts)
+        assert _say(acts) == [MSG_ASK_WAIT_TIME]
 
 
 class TestAskingStuckFallback:
diff --git a/src/vica_mission_manager/test/test_destination_change.py b/src/vica_mission_manager/test/test_destination_change.py
index ec0e035..378a6a7 100644
--- a/src/vica_mission_manager/test/test_destination_change.py
+++ b/src/vica_mission_manager/test/test_destination_change.py
@@ -129,7 +129,10 @@ class TestAnswers:
         assert navs[0].tree == NAV_TREE_GUIDED
 
     def test_silence_resumes_original(self):
+        """15초 조용하면 한 번 다시 묻고(2026-10-08 다시 묻기), 30초면 원래 목적지로."""
         logic, _ = asked_change(t=1.0)
+        assert logic.on_tick(15.9, NavStatus.NONE) == []
+        assert _say(logic.on_tick(16.0, NavStatus.NONE)) == ["화장실로 안내해드릴까요?"]
         assert logic.on_tick(1.0 + logic.confirm_timeout_sec - 0.1, NavStatus.NONE) == []
         actions = logic.on_tick(1.0 + logic.confirm_timeout_sec, NavStatus.NONE)
         assert logic.state == State.NAVIGATING and logic.active_destination == ROOM
diff --git a/src/vica_mission_manager/test/test_mission_logic.py b/src/vica_mission_manager/test/test_mission_logic.py
index 585ea37..6f21daa 100644
--- a/src/vica_mission_manager/test/test_mission_logic.py
+++ b/src/vica_mission_manager/test/test_mission_logic.py
@@ -225,8 +225,12 @@ class TestTransitions:
         assert any(isinstance(a, Navigate) for a in actions)
 
     def test_confirm_timeout_30s(self):
+        """15초 조용하면 같은 질문을 한 번 더(2026-10-08 다시 묻기), 30초면 접는다."""
         logic = MissionLogic(confirm_timeout_sec=30.0)
         logic.on_intent(make_intent(need_confirm=True), make_dest(), BOUNDS, True, 0.0)
+        reask = logic.on_tick(15.0, NavStatus.NONE)
+        assert [a.text for a in reask if isinstance(a, Say)] == [
+            "윤지영 교수님 사무실로 안내해드릴까요?"]
         assert logic.on_tick(29.9, NavStatus.NONE) == []
         assert logic.state == State.CONFIRMING
         actions = logic.on_tick(30.0, NavStatus.NONE)
@@ -733,10 +737,13 @@ class TestVoiceCancelConfirm:
         assert logic.cancel_confirm_pending is False
 
     def test_timeout_keeps_navigating(self):
-        # 응답이 없으면 취소하지 않고 안내를 이어간다.
+        # 응답이 없으면 15초에 한 번 다시 묻고(2026-10-08), 그래도 없으면 취소하지 않고
+        # 안내를 이어간다.
         logic = MissionLogic()
         start_navigation(logic)
         logic.on_cancel_confirm_request(1.0)
+        reask = logic.on_tick(16.0, NavStatus.RUNNING)
+        assert [a.text for a in reask if isinstance(a, Say)] == ["안내를 취소할까요?"]
         logic.on_tick(1.0 + logic.confirm_timeout_sec + 0.1, NavStatus.RUNNING)
         assert logic.cancel_confirm_pending is False
         assert logic.state == State.NAVIGATING
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 26ce239..25a9499 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -4,8 +4,8 @@
 """
 from reaction_states import (BOUNDS, ELEV, ROOM, SPOT_DEST, asking, asking_wait_time,
                              awaiting_user, confirming, idle_braked, intent, lookup, navigating,
-                             returning, returning_late, turning, waiting, waiting_asked,
-                             waiting_release)
+                             paused, returning, returning_late, turning, waiting,
+                             waiting_asked, waiting_release)
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
     MSG_APPROACH_ONBOARDING,
@@ -300,3 +300,69 @@ def test_unknown_destination_falls_back_to_onboarding():
                           lookup, BOUNDS, True)
     assert logic.state == State.TURNING
     assert _after_turn(logic, t + 4.0)[-1] == MSG_APPROACH_ONBOARDING
+
+
+# ---- Task 12: 다시 묻기 — 질문마다 한 번 -----------------------------------------
+def test_confirm_strange_answer_reasks_once():
+    logic, t = confirming()
+    ask = say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "화장실")
+    assert _says(logic.on_voice_intent(intent("unknown"), t, lookup, BOUNDS, True)) == [ask]
+    assert logic.on_voice_intent(intent("clarify"), t + 3, lookup, BOUNDS, True) == []
+    assert logic.state == State.CONFIRMING
+    # 이상한 답으로 다시 물었으면 15초 침묵에도 또 묻지 않는다 — 질문마다 한 번.
+    assert _says(logic.on_tick(t + 16, NavStatus.NONE)) == []
+
+
+def test_cancel_question_strange_answer_reasks_once():
+    logic, t = navigating()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    assert _says(logic.on_voice_intent(intent("unknown"), t + 2, lookup, BOUNDS, True)) == [
+        MSG_CANCEL_CONFIRM]
+    assert logic.on_voice_intent(intent("unknown"), t + 4, lookup, BOUNDS, True) == []
+    assert logic.cancel_confirm_pending
+
+
+def test_cancel_question_while_paused_now_times_out():
+    """예전엔 안내 주행 중에만 취소 확인 시계를 봐서 일시정지 중에 물은 확인이 끝나지 않았다."""
+    logic, t = paused()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    assert _says(logic.on_tick(t + 15, NavStatus.NONE)) == [MSG_CANCEL_CONFIRM]
+    logic.on_tick(t + 31, NavStatus.NONE)
+    assert not logic.cancel_confirm_pending and logic.state == State.PAUSED
+
+
+def test_where_question_reasks_once_then_keeps_waiting():
+    logic, t = waiting_asked()           # t-1 에 "네, 어디로 모실까요?"
+    assert _says(logic.on_tick(t + 14.5, NavStatus.NONE)) == [MSG_WAIT_FINISH_ASK]
+    later = logic.on_tick(t + 40, NavStatus.NONE)
+    assert MSG_WAIT_FINISH_ASK not in _says(later)
+    assert logic.state == State.WAITING
+
+
+def test_need_question_silence_reasks_then_keeps_waiting():
+    logic, t = waiting()
+    logic.on_voice_intent(intent("cancel"), t, lookup, BOUNDS, True)
+    assert _says(logic.on_tick(t + 15, NavStatus.NONE)) == [MSG_WAIT_NEED_ASK]
+    assert _says(logic.on_tick(t + 30, NavStatus.NONE)) == [MSG_CANCEL_KEPT]
+    assert logic.state == State.WAITING
+
+
+def test_late_tick_still_reasks_before_folding():
+    """틱이 늦게 와 다시 묻기 시각과 마감이 한 틱에 겹쳐도 먼저 다시 묻고 답할 시간을 남긴다."""
+    logic, t = confirming()
+    acts = logic.on_tick(t + 40, NavStatus.NONE)          # 15초도 30초도 지났다
+    assert _says(acts) == [say_destination(MSG_CONFIRM_PROMPT_FALLBACK, "화장실")]
+    assert logic.state == State.CONFIRMING
+    logic.on_tick(t + 40 + 15, NavStatus.NONE)
+    assert logic.state == State.IDLE
+
+
+def test_llm_clarify_is_not_a_strange_answer():
+    """LLM 이 되묻는 중(clarify)이면 미션은 끼어들지 않는다 — 두 목소리 방지. 못 알아들은
+    답(unknown)만 미션이 질문을 다시 한다."""
+    logic, t = asking()
+    assert logic.on_voice_intent(intent("clarify"), t, lookup, BOUNDS, True) == []
+    assert logic.state == State.ASKING_NEXT
+    logic, t = confirming()
+    assert logic.on_voice_intent(intent("clarify"), t, lookup, BOUNDS, True) == []
+    assert logic.state == State.CONFIRMING
diff --git a/src/vica_mission_manager/test/test_reaction_table.py b/src/vica_mission_manager/test/test_reaction_table.py
index f35f18d..5c41daa 100644
--- a/src/vica_mission_manager/test/test_reaction_table.py
+++ b/src/vica_mission_manager/test/test_reaction_table.py
@@ -332,8 +332,6 @@ EXPECT = {
 }
 
 PENDING = {
-    # Task 12
-    "WAITING_ASKED.yes": 12,
 }
 
 
diff --git a/src/vica_mission_manager/test/test_wait_spot.py b/src/vica_mission_manager/test/test_wait_spot.py
index f282ae8..4048f05 100644
--- a/src/vica_mission_manager/test/test_wait_spot.py
+++ b/src/vica_mission_manager/test/test_wait_spot.py
@@ -290,6 +290,7 @@ class TestTalkingWhileWaiting:
         nxt = _dest(id="d2", name="안내소")
         logic.on_intent(_intent(matched_destination_id="d2", need_confirm=True),
                         nxt, BOUNDS, True, 20.0)
+        logic.on_tick(20.0 + 15.0, NavStatus.NONE)     # 15초: 같은 질문 한 번 더(2026-10-08)
         logic.on_tick(20.0 + 31.0, NavStatus.NONE)
         assert logic.state == State.WAITING
         logic.on_intent(_intent(matched_destination_id="d2", need_confirm=True),
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: PENDING 의 마지막 1칸과 새 시험·고친 기존 시험이 실패한다. 결과 줄: `17 failed, 968 passed, 1 skipped`

- [ ] **Step 3: 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/12-code.patch"
```

<details><summary>12-code.patch (307줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index baaf00b..6bec7ae 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -457,6 +457,9 @@ MSG_WAIT_FINISH_ASK = "네, 어디로 모실까요?"
 # 대기 중 "취소" — 안내를 끝낼지 묻는다(2026-10-08 사용자 결정 3, 사용자 문구). 부정 질문이라
 # "네"(필요 없다) = 종료·홈, "아니요"(필요하다) = 계속 대기. 음성 쪽이 미리 굽는 글자와 같아야 한다.
 MSG_WAIT_NEED_ASK = "안내가 필요 없으신가요?"
+# 질문을 다시 묻기까지 기다리는 시간(2026-10-08 사용자 제안 "대답이 없거나 이상하면 다시
+# 묻기"). 다시 묻기는 질문마다 한 번이다 — 옆사람 말이 섞여도 끝없이 되풀이하지 않게.
+QUESTION_REASK_SEC = 15.0
 # 대기 장소 입구 기준 방향 → 멘트 속 장소 말. 상황판(RobotState.wait_place)에도 같은 말을 쓴다.
 WAIT_PLACE_PHRASES = {"right": "입구 오른쪽", "left": "입구 왼쪽", "across": "입구 맞은편"}
 # 대기 장소가 막혀 목적지로 돌아와 기다릴 때의 장소 말.
@@ -1400,6 +1403,8 @@ class MissionLogic:
         self._release_entered_at: Optional[float] = None
         self._wait_finish_asked_at: Optional[float] = None   # 대기 중 "어디로 모실까요?" 시각
         self._wait_need_asked_at: Optional[float] = None     # 대기 중 "안내가 필요 없으신가요?" 시각
+        self._wait_finish_reasked = False   # 대기 중 두 질문을 이미 다시 물었나 (2026-10-08)
+        self._wait_need_reasked = False
         # 대기 중에 목적지 '제안'이 와서 확인 질문(CONFIRMING)으로 들어갔을 때 돌아갈
         # 대기 상태. 거절·시간초과·호출이면 이 상태로 되돌아간다(대기 시간·장소 유지).
         self._wait_hold: Optional[State] = None
@@ -1413,6 +1418,11 @@ class MissionLogic:
         self._approach_dest: Optional[Destination] = None
         # 지금 확인 질문의 문장(2026-10-08 반응표). "다시 가자"·다시 묻기에서 같은 질문을 한다.
         self._confirm_prompt = ""
+        # 다시 묻기(2026-10-08): 확인 질문·취소 확인을 다시 물을 시각과 이미 다시 물었는지.
+        self._confirm_reask_at: Optional[float] = None
+        self._confirm_reasked = False
+        self._cancel_reask_at: Optional[float] = None
+        self._cancel_reasked = False
         # 지금 안내 주행의 행동 트리 종류. 재시도·재개가 같은 트리를 쓰게 한다.
         self._nav_tree: str = NAV_TREE_DEFAULT
         # 귀 상태 (/vica/listen_state). 무응답 판정 전에 귀 사정을 본다.
@@ -1506,6 +1516,12 @@ class MissionLogic:
         if self.cancel_confirm_pending and intent.intent in ("affirm", "deny"):
             # "안내를 취소할까요?"의 네·아니요 — 예전엔 접근 질문 배선으로 가서 버려졌다.
             return self.on_cancel_confirm_answer(intent.intent == "affirm", now)
+        if self.cancel_confirm_pending and intent.intent == "unknown":
+            # 취소 확인에 못 알아들은 답 — 한 번 다시 묻고, 그 뒤는 흘려보낸다(다시 묻기).
+            if not self._cancel_reasked:
+                self._cancel_reasked = True
+                return [self._ask(MSG_CANCEL_CONFIRM)]
+            return []
         handler = {
             State.IDLE: self._react_idle,
             State.CONFIRMING: self._react_confirming,
@@ -1570,14 +1586,28 @@ class MissionLogic:
             dest = lookup(self.confirming_dest_id or "")
             return self.on_confirm_answer(False, dest, bounds, nav_ready, now)
         if kind == "pause" and not change:
-            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._arm_confirm(now)
             return [self._ask(MSG_WAKE_GREETING)]
         if kind == "resume" and not change and self._confirm_prompt:
             # 물어 둔 질문에 "다시 가자" — 출발해도 되는지 같은 질문으로 다시 묻는다.
-            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._arm_confirm(now)
             return [self._ask(self._confirm_prompt)]
+        if kind == "unknown":
+            # 못 알아들은 답 — 같은 질문을 한 번 다시(2026-10-08 다시 묻기). 그 뒤의 이상한
+            # 답은 흘려보내고 시간이 다 되면 지금처럼 접는다. LLM 이 되묻는 중(clarify)이면
+            # 끼어들지 않는다 — 그 대화의 답이 곧 온다.
+            if not self._confirm_reasked and self._confirm_prompt:
+                self._confirm_reasked = True
+                return [self._ask(self._confirm_prompt)]
+            return []
         return None
 
+    def _arm_confirm(self, now: float) -> None:
+        """확인 질문 시계 — 15초 조용하면 같은 질문을 한 번 더, 30초면 접는다(2026-10-08)."""
+        self._confirm_deadline = now + self.confirm_timeout_sec
+        self._confirm_reask_at = now + QUESTION_REASK_SEC
+        self._confirm_reasked = False
+
     @staticmethod
     def _confirm_prompt_for(dest: Optional[Destination]) -> str:
         """목적지 확인 질문 문장. 목적지에 문장이 없으면 음성과 같은 기본 문장이다."""
@@ -1690,21 +1720,60 @@ class MissionLogic:
                 return [Say(MSG_CANCEL_KEPT, priority="response")]
             self._reset_arrival_dialog()
             return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
+        if self._wait_need_asked_at is not None and kind == "unknown":
+            # 못 알아들은 답 — 한 번 다시 묻고, 또 그러면 계속 기다린다(다시 묻기).
+            if not self._wait_need_reasked:
+                self._wait_need_reasked = True
+                self._wait_need_asked_at = now
+                return [self._ask(MSG_WAIT_NEED_ASK)]
+            self._wait_need_asked_at = None
+            return [Say(MSG_CANCEL_KEPT, priority="response")]
         if kind == "cancel":
             self._wait_need_asked_at = now
+            self._wait_need_reasked = False
             self._wait_finish_asked_at = None
             return [self._ask(MSG_WAIT_NEED_ASK)]
         asked = self._wait_finish_asked_at
-        if kind == "deny" and asked is not None and now - asked <= WAIT_FINISH_REPEAT_SEC:
+        within = asked is not None and now - asked <= WAIT_FINISH_REPEAT_SEC
+        if kind == "deny" and within:
             # "네, 어디로 모실까요?"에 "아니" — 갈 곳이 없다. "다 됐어"를 두 번 한 것과 같다.
             self._reset_arrival_dialog()
             return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
+        if within and kind in ("unknown", "affirm"):
+            # "어디로 모실까요?"에 못 알아들은 답·"네" — 한 번 다시 묻는다(다시 묻기).
+            if not self._wait_finish_reasked:
+                self._wait_finish_reasked = True
+                self._wait_finish_asked_at = now
+                return [self._ask(MSG_WAIT_FINISH_ASK)]
+            return []
         return None
 
+    def _wait_question_tick(self, now: float) -> list:
+        """대기 중 미션 질문의 다시 묻기(2026-10-08). 15초 조용하면 한 번 더 묻는다. "안내가
+        필요 없으신가요?"는 다시 물어도 조용하면 "안내를 계속하겠습니다." 하고 계속 기다린다."""
+        if self._ear_holds(now):
+            return []
+        asked = self._wait_finish_asked_at
+        if (asked is not None and not self._wait_finish_reasked
+                and now - asked >= QUESTION_REASK_SEC):
+            self._wait_finish_reasked = True
+            self._wait_finish_asked_at = now    # 두 번째 "다 됐어"의 30초 창도 다시 연다
+            return [self._ask(MSG_WAIT_FINISH_ASK)]
+        need = self._wait_need_asked_at
+        if need is not None and now - need >= QUESTION_REASK_SEC:
+            if not self._wait_need_reasked:
+                self._wait_need_reasked = True
+                self._wait_need_asked_at = now
+                return [self._ask(MSG_WAIT_NEED_ASK)]
+            self._wait_need_asked_at = None
+            return [Say(MSG_CANCEL_KEPT, priority="response")]
+        return []
+
     def _ask_where(self, now: float) -> list:
         """대기 중 "다시 가자" — 어디로 갈지 묻는다. "다 됐어"의 첫 질문과 같은 문장이지만
         두 번 말해도 안내를 끝내지 않는다(그건 "다 됐어"만)."""
         self._wait_finish_asked_at = now
+        self._wait_finish_reasked = False
         self._wait_need_asked_at = None
         return [self._ask(MSG_WAIT_FINISH_ASK)]
 
@@ -1923,7 +1992,7 @@ class MissionLogic:
                     self._wait_hold = self.state
                 self.state = State.CONFIRMING
                 self._confirming_dest_id = intent.matched_destination_id or None
-                self._confirm_deadline = now + self.confirm_timeout_sec
+                self._arm_confirm(now)
                 self._confirm_prompt = self._confirm_prompt_for(dest)
                 return []
 
@@ -1942,7 +2011,7 @@ class MissionLogic:
                 return [Say(msg, priority="response")] if msg else []
             assert dest is not None  # check_gate 가 보장
             self._confirming_dest_id = dest.id
-            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._arm_confirm(now)
             self._confirm_prompt = self._confirm_prompt_for(dest)
             return [self._ask(MSG_CONFIRM_SWITCH.format(prompt=self._confirm_prompt))]
 
@@ -2059,7 +2128,7 @@ class MissionLogic:
         self.active_destination = None
         self.state = State.CONFIRMING
         self._confirming_dest_id = new_id
-        self._confirm_deadline = now + self.confirm_timeout_sec
+        self._arm_confirm(now)
         self._confirm_prompt = self._confirm_prompt_for(dest)
         # 앞서 물은 "안내를 취소할까요?"는 이 질문으로 대체됐다 — 남기면 새 목적지로
         # 출발한 뒤 "취소" 한마디가 되묻지 않고 바로 취소된다(2026-10-07 검토).
@@ -2084,6 +2153,8 @@ class MissionLogic:
             self._reset_arrival_dialog()
             return [Say(MSG_FINISH, priority="response"), *self._go_home(now)]
         self._wait_finish_asked_at = now
+        self._wait_finish_reasked = False
+        self._wait_need_asked_at = None
         return [Say(MSG_WAIT_FINISH_ASK, priority="response", expects_reply=True)]
 
     def _changing_destination(self) -> bool:
@@ -2496,10 +2567,27 @@ class MissionLogic:
             return [], reason
         self.cancel_confirm_pending = True
         self._cancel_confirm_deadline = now + self.confirm_timeout_sec
+        self._cancel_reask_at = now + QUESTION_REASK_SEC
+        self._cancel_reasked = False
         return [
             Say(MSG_CANCEL_CONFIRM, priority="response", expects_reply=True)
         ], GateReason.OK
 
+    def _cancel_confirm_tick(self, now: float) -> list:
+        """"안내를 취소할까요?" 시계. 15초 조용하면 한 번 다시 묻고(2026-10-08 다시 묻기), 시간이
+        다 되면 조용히 하던 대로 둔다(2026-09-01 감량, 취소하지 않는다). 예전엔 안내 주행 중에만
+        시계를 봐서 일시정지·바꾸기 질문 중에 물은 확인은 끝나지 않았다."""
+        if (not self._cancel_reasked and self._cancel_reask_at is not None
+                and now >= self._cancel_reask_at and not self._ear_holds(now)):
+            self._cancel_reasked = True
+            self._cancel_confirm_deadline = max(self._cancel_confirm_deadline or now,
+                                                now + QUESTION_REASK_SEC)
+            return [self._ask(MSG_CANCEL_CONFIRM)]
+        if self._cancel_confirm_deadline is not None and now >= self._cancel_confirm_deadline:
+            self.cancel_confirm_pending = False
+            self._cancel_confirm_deadline = None
+        return []
+
     def on_cancel_confirm_answer(self, affirmative: bool, now: float) -> list:
         """취소 재확인에 대한 응답. 긍정이면 실제로 취소한다."""
         if not self.cancel_confirm_pending:
@@ -2676,7 +2764,7 @@ class MissionLogic:
             # 접근 질문에 목적지로 답했다 — 온보딩 대신 그 목적지를 확인한다(2026-10-08 반응표).
             self.state = State.CONFIRMING
             self._confirming_dest_id = approach_dest.id
-            self._confirm_deadline = now + self.confirm_timeout_sec
+            self._arm_confirm(now)
             self._confirm_prompt = self._confirm_prompt_for(approach_dest)
             actions.append(self._ask(self._confirm_prompt))
             return actions
@@ -3315,7 +3403,9 @@ class MissionLogic:
         # 사다리를 쓰지 않는다: 미션까지 "잘 듣지 못했습니다…"를 얹으면 두 목소리가 나고
         # 재질문 한 번을 헛되이 쓴다(2026-10-07 검토 — 호출 뒤 질문 유지·도착 방향 답이
         # 이 길을 자주 만든다). 8초 시계는 LLM 대답의 재생이 끝날 때 다시 돈다.
-        if kind == "question":
+        # LLM 이 되묻는 중(clarify, "어느 화장실이요?")도 같다 — 미션까지 다시 물으면 두 목소리가
+        # 난다(2026-10-08 반응표). 못 알아들은 답(unknown)만 아래 사다리로 간다.
+        if kind in ("question", "clarify"):
             self._response_deadline = None
             self._asking_entered_at = now
             return []
@@ -3515,12 +3605,16 @@ class MissionLogic:
         return actions
 
     def _arrival_no_answer(self, now: float) -> list:
-        """무응답 사다리: 못 알아들으면 1회 재질문, 그 뒤엔 떠나기 예고."""
+        """무응답 사다리: 못 알아들으면 같은 질문을 1회 다시 묻고, 그 뒤엔 떠나기 예고.
+
+        2026-10-08 다시 묻기: 예전엔 "잘 듣지 못했습니다. 계속 안내가 필요하시면 말씀해
+        주세요."였다 — 사용자는 질문을 다시 들어야 답할 수 있다. 물어 둔 질문이 없으면
+        (늦은 답 그물의 대화) 옛 문장을 쓴다."""
         if not self._arrival_retried:
             self._arrival_retried = True
             self._response_deadline = None
             self._asking_entered_at = now   # 재질문도 새 시계 유실 폴백 기준
-            return [Say(MSG_ARRIVAL_RETRY, priority="response", expects_reply=True)]
+            return [self._ask(self._asking_question or MSG_ARRIVAL_RETRY)]
         return self._leaving_notice(now)
 
     def _arrival_silence(self, now: float) -> list:
@@ -3661,6 +3755,8 @@ class MissionLogic:
         self._release_entered_at = None
         self._wait_finish_asked_at = None
         self._wait_need_asked_at = None
+        self._wait_finish_reasked = False
+        self._wait_need_reasked = False
         self._wait_hold = None
 
     def _forget_interrupted_return(self) -> None:
@@ -3748,8 +3844,20 @@ class MissionLogic:
                 return handle_actions
             actions.extend(handle_actions)
 
+        if self.cancel_confirm_pending:
+            actions.extend(self._cancel_confirm_tick(now))
+
         if self.state == State.CONFIRMING:
-            if self._confirm_deadline is not None and now >= self._confirm_deadline:
+            if (not self._confirm_reasked and self._confirm_prompt
+                    and self._confirm_reask_at is not None and now >= self._confirm_reask_at
+                    and not self._ear_holds(now)):
+                # 확인 질문에 15초 답이 없다 — 같은 질문을 한 번 더 묻는다(2026-10-08 다시 묻기).
+                # 다시 물은 뒤에도 답할 시간을 남긴다(틱이 늦게 와도).
+                self._confirm_reasked = True
+                self._confirm_deadline = max(self._confirm_deadline or now,
+                                             now + QUESTION_REASK_SEC)
+                actions.append(self._ask(self._confirm_prompt))
+            elif self._confirm_deadline is not None and now >= self._confirm_deadline:
                 if self._change_from is not None:
                     # 주행 중 바꾸기 질문에 답이 없다 — 원래 목적지로 다시 출발한다
                     # (2026-10-07 사용자 결정, 아니요와 같은 길·같은 멘트).
@@ -3759,16 +3867,7 @@ class MissionLogic:
                     actions.append(Say(MSG_CONFIRM_TIMEOUT))
 
         elif self.state == State.NAVIGATING:
-            # 취소 재확인에 답이 없으면 주행을 그대로 이어간다(취소하지 않는다).
-            if (
-                self.cancel_confirm_pending
-                and self._cancel_confirm_deadline is not None
-                and now >= self._cancel_confirm_deadline
-            ):
-                self.cancel_confirm_pending = False
-                self._cancel_confirm_deadline = None
-                # "이어갑니다" 멘트는 2026-09-01 감량 — 답 안 했으면 조용히 계속.
-
+            # 취소 재확인의 시계는 위 _cancel_confirm_tick 이 본다(어느 상태에서 물었든).
             if nav_status == NavStatus.SUCCEEDED:
                 dest = self.active_destination
                 text = (
@@ -4049,7 +4148,12 @@ class MissionLogic:
                     and not self._ear_holds(now)):
                 actions.extend(self._wait_expired(now))
             else:
-                actions.extend(self._beacon_tick(now))
+                # 질문을 다시 묻는 틱에는 M3 를 얹지 않는다 — 다음 틱의 M3 는 ambient 라 질문이
+                # 나가는 동안 TTS 가 버린다.
+                asked = self._wait_question_tick(now)
+                actions.extend(asked)
+                if not asked:
+                    actions.extend(self._beacon_tick(now))
 
         elif self.state == State.RETURNING:
             # 복귀 실패도 완료로 친다. 대기 위치에 못 갔다고 접근 상태에 갇히면
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 982 passed, 1 skipped` (실패 3개는 `test_progress_narration.py`의 원래 실패)

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_arrival_dialog.py src/vica_mission_manager/test/test_destination_change.py src/vica_mission_manager/test/test_mission_logic.py src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/test/test_reaction_table.py src/vica_mission_manager/test/test_wait_spot.py src/vica_mission_manager/vica_mission_manager/mission_logic.py
git -C vica_ros2_ws commit -m "feat(mission): 질문마다 한 번 다시 묻기 — 확인·취소 확인·도착 질문·대기 중 질문(사용자 제안 10-08)" -m "$VICA_TRAILER"
```


### Task 13: 음성 — LLM 은 로봇이 할 일을 약속하지 않는다(지시문)

규칙 2와 LLM 규칙 넷. 소리 지시문(`build_audio_prompt`)·텍스트 지시문(`_build_system_prompt`)·로컬 규칙
(`LOCAL_PROMPT_RULES` 1번)을 고친다.
1. 약속 금지: question·clarify·unknown 의 reply 는 정보와 되묻기까지만. 목록에 있는 곳을 권하려면 navigate(need_confirm=true).
2. 접근 질문에 목적지로 답하면 navigate(need_confirm=true, reply="") — 옛 "반드시 affirm/deny"(903) 막음을 푼다.
3. "기다리지 마"·"대기 안 해도 돼": 대기를 묻는 질문 뒤면 deny, "안내를 마칠까요?" 뒤면 affirm.
4. "안내가 필요 없으신가요?"는 뜻으로: 필요 없다는 뜻 = affirm, 필요하다는 뜻 = deny.
5. 로봇이 질문 중인데 못 알아들었으면 unknown, reply="" — 로봇 본체가 다시 묻는다(옛: clarify 로 그 질문을 직접 다시).
확신이 낮을 때의 규칙도 같은 뜻으로 바꾼다. 바꾸는 글은 모두 지시문 앞쪽의 고정 글이라 캐시 접두 시험
(8할 공통)은 그대로 통과한다.

**Files:**
- Create: `vica-voice-llm/tests/test_mission_reactions_voice.py`
- Modify: `vica-voice-llm/src/langchain_intent_parser.py`
- Modify: `vica-voice-llm/src/local_rules.py`

**Interfaces:**
- Produces: 지시문 문장(시험이 글자로 확인)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/13-test.patch"
```

<details><summary>13-test.patch (46줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_mission_reactions_voice.py b/tests/test_mission_reactions_voice.py
new file mode 100644
index 0000000..148f233
--- /dev/null
+++ b/tests/test_mission_reactions_voice.py
@@ -0,0 +1,40 @@
+"""미션 요청 반응표(2026-10-08) — 음성 쪽: LLM 지시문(규칙 2)·미션 질문 중 대답·문장.
+
+정본 설계: docs/superpowers/specs/2026-10-08-mission-request-reactions-design.md 8절.
+"""
+from src import langchain_intent_parser as parser
+from src import local_rules
+from src.langchain_intent_parser import _build_system_prompt
+from src.schema import DestinationData
+
+DEST = DestinationData(id="wc", name="화장실", confirm_prompt="화장실로 안내해드릴까요?")
+
+
+# ---- Task 13: 지시문 --------------------------------------------------------------
+class TestPromptRules:
+    def test_audio_prompt_allows_destination_answer_to_approach_question(self):
+        text = parser.build_audio_prompt([DEST])
+        assert "그 답은 반드시" not in text          # 옛 "반드시 affirm/deny" 막음
+        assert 'navigate(need_confirm=true, reply="")로 낸다' in text
+
+    def test_audio_prompt_has_wait_refusal_and_negative_question(self):
+        text = parser.build_audio_prompt([DEST])
+        assert "기다리지 마" in text and "안내가 필요 없으신가요?" in text
+        assert '"아니, 필요 없어"' in text
+
+    def test_audio_prompt_bans_promises(self):
+        text = parser.build_audio_prompt([DEST])
+        assert "약속 금지" in text and "계속 안내할까요?" in text
+
+    def test_audio_prompt_leaves_reasking_to_the_mission(self):
+        text = parser.build_audio_prompt([DEST])
+        assert "로봇 본체가 같은 질문을 한 번 다시 한다" in text
+        assert "그 질문을 다시(\"여기서 기다릴까요?\")" not in text
+
+    def test_text_prompt_has_the_same_rules(self):
+        text = _build_system_prompt([DEST])
+        for key in ("목적지로 답하면", "기다리지 마", "안내가 필요 없으신가요?", "계속 안내할까요?"):
+            assert key in text, key
+
+    def test_local_rule_allows_destination_answer(self):
+        assert "목적지를 말하면 navigate" in local_rules.LOCAL_PROMPT_RULES
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: 새 시험 6개가 실패한다(지시문 글이 아직 옛 것). 결과 줄: `6 failed, 750 passed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/13-code.patch"
```

<details><summary>13-code.patch (95줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/langchain_intent_parser.py b/src/langchain_intent_parser.py
index 335072e..3b87ecc 100644
--- a/src/langchain_intent_parser.py
+++ b/src/langchain_intent_parser.py
@@ -177,6 +177,10 @@ def _build_system_prompt(
 - affirm / deny: 로봇이 직전에 던진 안내 제안 질문("안내가 필요하신가요?" 등)에
   대한 수락/거절 ("어… 부탁드려요"->affirm, "괜찮아요, 됐어요"->deny).
   목적지 확인 질문의 답이 아니라, 안내 자체를 받겠냐는 제안에 대한 답일 때만.
+  "안내를 받으시겠어요?"에 목적지로 답하면("응, 화장실 가고 싶어") affirm 이 아니라 navigate 다.
+  "기다리지 마"·"대기 안 해도 돼"는 대기를 묻는 질문 뒤면 deny, "안내를 마칠까요?" 뒤면 affirm.
+  "안내가 필요 없으신가요?"는 부정 질문이라 뜻으로 고른다 — 필요 없다는 뜻("네", "아니, 필요 없어",
+  "괜찮아")은 affirm, 필요하다는 뜻("아니요", "필요해")은 deny.
 - wait: 목적지 도착 후 여기서 기다려 달라는 요청 ("좀 있다 올게", "잠깐 여기 있어").
 - finish: 오늘 안내를 다 끝내려 함 ("이제 됐어 고마워", "그만 갈게"). 도착 후
   전체 종료다. cancel(주행 중간에 이 목적지만 그만)과 구분하라.
@@ -190,7 +194,9 @@ def _build_system_prompt(
 - destination_candidate 는 위 목록의 정확한 name 또는 null. 새로 지어내지 마라.
 - navigate(destination_candidate 포함)·cancel·pause·resume·affirm·deny·wait·finish 로
   분류하면 reply 는 빈 문자열로 둬라. 확인·수락 발화는 시스템이 만든다.
-- 그 외(question/clarify/unknown)의 reply 는 짧고 친절한 한국어로 써라.
+- 그 외(question/clarify/unknown)의 reply 는 짧고 친절한 한국어로 써라. 정보와 되묻기까지만이다 —
+  "알겠습니다"·"할게요" 같은 약속, "안내해드릴까요?"·"계속 안내할까요?"처럼 로봇이 할 일을 권하는
+  말은 쓰지 않는다(로봇 본체가 모르는 약속이 된다). 목록에 있는 곳을 권하려면 navigate 로 내라.
 - 확신이 없으면 confidence 를 낮춰라.
 
 [지금 상황 쓰기] 맨 뒤에 [지금 상황]이 있으면 미션이 확인한 사실이다.
@@ -899,10 +905,17 @@ reply="" 로 답한다. 이력에 있는 말을 베껴 적지 마라 — 이번
   부정 뒤에 **목록에 없는 곳**을 말하면("아니, 학과장님 사무실") 방금 거절당한 목적지를 그대로 다시
   제안하지 마라 — 로봇 본체는 같은 곳의 재제안을 승낙으로 보고 출발한다(21:21 실기). clarify 로
   "학과장님 사무실은 목록에 없어요. 학과사무실이 맞을까요?"처럼 되묻는다.
+  "기다리지 마"·"대기 안 해도 돼"는 대기를 거절하는 말이다: 로봇의 마지막 말이 대기를 묻는 질문
+  ("…여기서 기다릴까요?"·"여기서 대기할까요?"·"몇 분쯤 걸리실까요?")이면 deny, "여기까지 안내를
+  마칠까요?"처럼 끝낼지 묻는 질문이면 affirm 이다(2026-10-08 실기 "대기하지 마").
+  로봇의 마지막 말이 "안내가 필요 없으신가요?"이면 글자가 아니라 뜻으로 고른다 — 필요 없다는 뜻
+  ("네", "응", "필요 없어", "아니, 필요 없어", "괜찮아", "됐어")은 affirm, 필요하다는 뜻("아니요",
+  "필요해", "더 기다려 줘")은 deny. reply="".
 - affirm: 로봇의 제안 질문("안내를 받으시겠어요?", "여기서 기다릴까요?", "여기서 대기할까요?")에 긍정. reply="".
-  **로봇의 마지막 말이 "…안내를 받으시겠어요?"(사람에게 다가가 건 첫 질문)이면 그 답은 반드시
-  affirm/deny 다** — 그 전에 네가 "OO로 안내해드릴까요?"라고 물었던 것과 무관하다. 여기서 navigate
-  를 내면 로봇 본체가 "지금은 다른 응대 중입니다"라며 거절한다(21:11·21:25 실기). "네. 네." 도 affirm.
+  로봇의 마지막 말이 "…안내를 받으시겠어요?"(사람에게 다가가 건 첫 질문)이면 긍정은 affirm, 부정은
+  deny 다 — 그 전에 네가 "OO로 안내해드릴까요?"라고 물었던 것과 무관하다. "네. 네." 도 affirm. 그
+  질문에 목적지로 답하면("응, 화장실 가고 싶어") navigate(need_confirm=true, reply="")로 낸다 — 로봇
+  본체가 수락으로 받고, 돌아서 손잡이를 내준 뒤 그 목적지를 직접 묻는다(2026-10-08).
 - wait: 도착 뒤 기다려 달라는 말이나 시간("오 분", "한 10분에서 15분", "반시간"). wait_minutes 에 분을 넣는다
   (범위면 큰 쪽, 시간이 없으면 null). "몇 분쯤 걸리실까요?"의 답은 시간만 말해도 wait 다. reply="".
 - finish: 도착 뒤 오늘 안내를 다 끝낸다("이제 됐어 고마워", "그만 갈게"). reply="".
@@ -925,13 +938,17 @@ reply="" 로 답한다. 이력에 있는 말을 베껴 적지 마라 — 이번
   "아까 어디 갔었지?"는 직전에 간 곳, "어디 가려고 했더라?"는 하려다 만 곳, "몇 시야?"는 시각,
   "배터리 얼마나 남았어?"는 배터리 줄로 답한다. 줄이 "모름"이면 한 문장으로 모른다고 한다. 정말 모르는 것만 한 문장으로 모른다고 한다 —
   안내 데스크·관리자에게 물어보라는 식의 조언은 하지 않는다.
+- 약속 금지(question·clarify·unknown 공통, 2026-10-08): reply 는 정보와 되묻기까지만이다. "알겠습니다"·
+  "할게요"·"해 드릴게요" 같은 약속, "계속 안내할까요?"·"방향 맞춰드릴까요?"처럼 로봇이 할 일을 권하는
+  말은 쓰지 않는다 — 로봇 본체가 모르는 약속이 된다. 목록에 있는 곳으로 안내를 권하려면 question 이
+  아니라 navigate(need_confirm=true)로 낸다(위 위치 질문 규칙처럼).
 - clarify: 어디로 갈지 모호하거나 목록에 없는 곳. reply 에 되묻는 질문(반드시 "?"로 끝).
-- unknown + 침묵(reply=""): 로봇에게 한 말이 **아닌 것이 분명할 때만** — 다른 사람들끼리의
-  대화, 기침·소음, 로봇 자신의 목소리. 그 외에는 침묵하지 마라(2026-09-20 사용자: 아무 말도
-  안 하면 무슨 상황인지 알 수 없다). 로봇이 방금 질문하고 답을 기다리는 중이거나 사용자가
-  로봇에게 말한 것 같은데 못 알아들었으면 intent=clarify 로 짧게 되묻는다 — 답을 기다리던
-  질문이 있으면 그 질문을 다시("여기서 기다릴까요?"), 없으면 "잘 못 들었어요. 다시 말씀해
-  주시겠어요?". 호출어 "비카야"만 들리면 로봇을 부른 것이다 — intent=unknown, reply 는
+- unknown + 침묵(reply=""): 로봇에게 한 말이 **아닌 것이 분명할 때**(다른 사람들끼리의 대화,
+  기침·소음, 로봇 자신의 목소리), 그리고 **로봇이 방금 질문하고 답을 기다리는데 못 알아들었을
+  때**다. 질문 중이면 로봇 본체가 같은 질문을 한 번 다시 한다 — 네가 또 물으면 두 목소리가 된다
+  (2026-10-08). 로봇이 묻고 있지 않은데 사용자가 로봇에게 말한 것 같고 못 알아들었으면 침묵하지
+  말고 intent=clarify 로 "잘 못 들었어요. 다시 말씀해 주시겠어요?"(2026-09-20 사용자: 아무 말도
+  안 하면 무슨 상황인지 알 수 없다). 호출어 "비카야"만 들리면 로봇을 부른 것이다 — intent=unknown, reply 는
   "{WAKE_GREETING}" 나 "네, 말씀하세요." 같은 짧은 응답.
 
 [목적지 목록] destination_candidate 는 반드시 아래 name 중 하나. 목록에 없는 곳은 clarify.
@@ -943,8 +960,8 @@ reply="" 로 답한다. 이력에 있는 말을 베껴 적지 마라 — 이번
 "엘리베이터로 가시면 돼요" 한 문장.
 
 [확신이 낮을 때] 안내를 끝내거나 접는 결정(deny·finish·cancel, 확정 navigate)은 되돌리기 어렵다.
-들린 말이 짧고 불분명해 confidence 가 0.7 미만이면 그 결정을 내리지 말고 clarify 로 로봇의
-마지막 질문을 다시 한다. "그럴래?"·"그럴까?"·"어어"처럼 부드러운 긍정을 부정으로 오해하지 마라.
+들린 말이 짧고 불분명해 confidence 가 0.7 미만이면 그 결정을 내리지 말고 intent=unknown,
+reply="" 로 둔다 — 로봇 본체가 마지막 질문을 다시 한다(2026-10-08). "그럴래?"·"그럴까?"·"어어"처럼 부드러운 긍정을 부정으로 오해하지 마라.
 
 [숫자] "테스트1·테스트2·테스트3"처럼 숫자로 갈리는 목적지는 숫자가 핵심이다. "쓰리·스리·삼"=3,
 "투·이"=2, "원·일"=1. 숫자가 확실치 않으면 confidence 를 낮추고 clarify 로 몇 번인지 되묻는다.
diff --git a/src/local_rules.py b/src/local_rules.py
index 4209a4c..2457a84 100644
--- a/src/local_rules.py
+++ b/src/local_rules.py
@@ -32,7 +32,7 @@ LOCAL_NUM_CTX = int(os.environ.get("VICA_LOCAL_NUM_CTX", "4096"))
 # 맞추지 않는다 — 작은 모델은 글이 길수록 느려지고 규칙을 놓친다.
 LOCAL_PROMPT_RULES = """
 [로컬 추가 규칙 — 이 규칙이 위 규칙보다 먼저다]
-1. 로봇의 마지막 말이 "안내를 받으시겠어요?"면 답은 affirm 또는 deny 만 고른다.
+1. 로봇의 마지막 말이 "안내를 받으시겠어요?"면 답은 affirm 또는 deny 다. 목적지를 말하면 navigate.
 2. 로봇의 마지막 말이 "여기서 대기할까요?"·"안내를 마칠까요?" 같은 도착 질문이면
    답은 affirm·deny·wait·finish 만 고른다. 목적지를 다시 제안하지 않는다.
 3. 사용자가 시간만 말하면("한 5분?", "십 분") intent 는 wait 다.
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `756 passed` 

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica-voice-llm add tests/test_mission_reactions_voice.py src/langchain_intent_parser.py src/local_rules.py
git -C vica-voice-llm commit -m "feat(voice): LLM 은 할 일을 약속하지 않는다 — 반응표 규칙 2, 접근 질문 목적지 답·기다리지 마·부정 질문 판정" -m "$VICA_TRAILER"
```


### Task 14: 음성 — 미션이 질문 중이면 못 알아들은 답에 LLM 이 말하지 않는다

규칙 2·다시 묻기의 짝. 새 모듈 `src/mission_question.py`(순수 함수 — `ros_node`는 rclpy 없이 시험할 수
없다). "미션이 질문 중" = dialog_state 가 확인·도착·시간·접근 질문이거나, 마지막 로봇 말(40초 안)이
"네, 어디로 모실까요?"·"안내가 필요 없으신가요?"·"안내를 취소할까요?"인 때. 그때 unknown 의 reply 를 지운다
("네?"·긴급은 그대로). 접근 질문·돌아서기 중 목적지 제안의 LLM 확인 질문도 지운다(미션이 돌아선 뒤 묻는다).
clarify·question 은 지우지 않는다.

`ros_node._publish_intent`에서 로컬 못 알아들음 규칙 뒤에 적용하고, 지운 대답은 텍스트 모드 기록에 빈 줄로
남기지 않는다 — 물어 둔 질문이 마지막 로봇 말로 남아야 다음 "네"가 그 답이 된다.

**Files:**
- Modify: `vica-voice-llm/tests/test_mission_reactions_voice.py`
- Modify: `vica-voice-llm/src/mission_phrases.py`
- Create: `vica-voice-llm/src/mission_question.py`
- Modify: `vica-voice-llm/src/ros_node.py`

**Interfaces:**
- Produces: `src/mission_question.py` — `MISSION_QUESTIONS`, `ASK_FRESH_SEC = 40.0`, `mission_is_asking(dialog_state, last_robot_text, last_robot_age_sec) -> bool`, `quiet_for_mission(intent, dialog_state, last_robot_text, last_robot_age_sec) -> VicaIntent`
- Produces: `mission_phrases.WAIT_NEED_ASK`(미션 `MSG_WAIT_NEED_ASK` 사본)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/14-test.patch"
```

<details><summary>14-test.patch (64줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_mission_reactions_voice.py b/tests/test_mission_reactions_voice.py
index 148f233..f5153fa 100644
--- a/tests/test_mission_reactions_voice.py
+++ b/tests/test_mission_reactions_voice.py
@@ -5,7 +5,10 @@
 from src import langchain_intent_parser as parser
 from src import local_rules
 from src.langchain_intent_parser import _build_system_prompt
-from src.schema import DestinationData
+from src.mission_phrases import WAIT_FINISH_ASK, WAIT_NEED_ASK
+from src.mission_question import mission_is_asking, quiet_for_mission
+from src.replies import CANCEL_CONFIRM, RETRY_PROMPT, WAKE_GREETING
+from src.schema import DestinationData, VicaIntent
 
 DEST = DestinationData(id="wc", name="화장실", confirm_prompt="화장실로 안내해드릴까요?")
 
@@ -38,3 +41,47 @@ class TestPromptRules:
 
     def test_local_rule_allows_destination_answer(self):
         assert "목적지를 말하면 navigate" in local_rules.LOCAL_PROMPT_RULES
+
+
+# ---- Task 14: 미션이 질문 중이면 LLM 은 말하지 않는다 --------------------------------
+def _i(kind, reply, need_confirm=False, safety="normal"):
+    return VicaIntent(intent=kind, reply=reply, need_confirm=need_confirm, safety_flag=safety)
+
+
+class TestQuietForMission:
+    def test_question_states_are_asking(self):
+        for state in ("confirming", "asking_next", "asking_wait_time", "awaiting_user"):
+            assert mission_is_asking(state, "", 999.0), state
+        assert not mission_is_asking("navigating", "", 1.0)
+
+    def test_mission_questions_in_waiting_count_while_fresh(self):
+        for q in (WAIT_FINISH_ASK, WAIT_NEED_ASK, CANCEL_CONFIRM):
+            assert mission_is_asking("waiting", q, 10.0), q
+            assert not mission_is_asking("waiting", q, 41.0), q
+
+    def test_unknown_reply_is_silenced_while_asking(self):
+        out = quiet_for_mission(_i("unknown", RETRY_PROMPT), "asking_next", "", 1.0)
+        assert out.intent == "unknown" and out.reply == ""
+
+    def test_clarify_and_question_keep_their_words(self):
+        """LLM 이 되묻거나 정보로 답하면 그대로 — 미션도 그때는 끼어들지 않는다."""
+        for kind in ("clarify", "question"):
+            out = quiet_for_mission(_i(kind, "어느 화장실이요?"), "confirming", "", 1.0)
+            assert out.reply == "어느 화장실이요?", kind
+
+    def test_wake_greeting_and_emergency_are_kept(self):
+        assert quiet_for_mission(_i("unknown", WAKE_GREETING), "asking_next", "", 1.0).reply
+        assert quiet_for_mission(_i("unknown", "멈춥니다", safety="emergency"),
+                                 "asking_next", "", 1.0).reply
+
+    def test_not_asking_keeps_the_reply(self):
+        out = quiet_for_mission(_i("unknown", RETRY_PROMPT), "idle", "", 1.0)
+        assert out.reply == RETRY_PROMPT
+
+    def test_destination_answer_to_approach_is_left_to_the_mission(self):
+        out = quiet_for_mission(_i("navigate", "화장실로 안내해드릴까요?", need_confirm=True),
+                                "awaiting_user", "", 1.0)
+        assert out.reply == ""
+        kept = quiet_for_mission(_i("navigate", "화장실로 안내해드릴까요?", need_confirm=True),
+                                 "idle", "", 1.0)
+        assert kept.reply == "화장실로 안내해드릴까요?"
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `tests/test_mission_reactions_voice.py` 수집 오류 — `ModuleNotFoundError: No module named 'src.mission_question'`. 결과 줄: `a445c/scratchpad/proto/wt/tmpfumd1m8r/vica-voice-llm/src/mission_phrases.py)
=========================== short test summary info ============================
ERROR tests/test_mission_reactions_voice.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/14-code.patch"
```

<details><summary>14-code.patch (102줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/mission_phrases.py b/src/mission_phrases.py
index 4de0837..5a679dc 100644
--- a/src/mission_phrases.py
+++ b/src/mission_phrases.py
@@ -40,6 +40,10 @@ WAIT_FINISH_ASK = "네, 어디로 모실까요?"
 # 비상 정지 중 "비카야" — "네?" 없이 이 한 마디만(호출 반응표).
 ESTOP_WAKE = "지금은 비상 멈춤 상태입니다."
 
+# ---- 미션 요청 반응표 (2026-10-08) --------------------------------------------------
+# 대기 중 "취소" — 안내를 끝낼지 묻는다(사용자 결정 3, 사용자 문구).
+WAIT_NEED_ASK = "안내가 필요 없으신가요?"
+
 # 숫자로 끝나는 이름을 읽을 때 마지막 숫자의 받침(영·일·삼·육·칠·팔 있음, 이·사·오·구 없음).
 _DIGIT_HAS_BATCHIM = {
     "0": True, "1": True, "2": False, "3": True, "4": False,
diff --git a/src/mission_question.py b/src/mission_question.py
new file mode 100644
index 0000000..91ee3ed
--- /dev/null
+++ b/src/mission_question.py
@@ -0,0 +1,42 @@
+"""미션이 질문 중일 때 LLM 대답을 줄이는 판단 (미션 요청 반응표 2026-10-08, 규칙 2·다시 묻기).
+
+미션은 질문마다 못 알아들은 답(unknown)에 같은 질문을 한 번 다시 한다. 그때 LLM 까지 말하면
+두 목소리가 된다 — 그래서 LLM 의 unknown 대답을 지운다. 접근 질문·돌아서기 중의 목적지 답은
+미션이 수락으로 받고 돌아선 뒤 직접 확인하므로 LLM 의 확인 질문도 지운다. LLM 이 되묻는
+clarify("어느 화장실이요?")는 지우지 않는다 — 미션도 그때는 끼어들지 않는다.
+ros_node 는 rclpy 없이 시험할 수 없어 판단은 여기 순수 함수로 둔다.
+"""
+from __future__ import annotations
+
+from .local_rules import ANSWER_WAIT_STATES
+from .mission_phrases import WAIT_FINISH_ASK, WAIT_NEED_ASK
+from .replies import CANCEL_CONFIRM, WAKE_GREETING
+
+# 대기 중·주행 중에도 미션이 묻는 질문 — dialog_state 만으로는 질문 중인지 모른다.
+MISSION_QUESTIONS = frozenset({WAIT_FINISH_ASK, WAIT_NEED_ASK, CANCEL_CONFIRM})
+# 그 질문의 답을 기다리는 시간 — 음성 질문 뒤 문맥 창(ros_node.FOLLOWUP_CONTEXT_SEC)과 같다.
+ASK_FRESH_SEC = 40.0
+# 미션이 수락 뒤 직접 목적지를 묻는 단계 — LLM 의 확인 질문은 겹친다.
+APPROACH_ANSWER_STATES = frozenset({"awaiting_user", "turning"})
+
+
+def mission_is_asking(dialog_state: str, last_robot_text: str, last_robot_age_sec: float) -> bool:
+    """미션이 사용자 대답을 기다리는 중인가."""
+    if dialog_state in ANSWER_WAIT_STATES:
+        return True
+    return ((last_robot_text or "").strip() in MISSION_QUESTIONS
+            and last_robot_age_sec <= ASK_FRESH_SEC)
+
+
+def quiet_for_mission(intent, dialog_state: str, last_robot_text: str,
+                      last_robot_age_sec: float):
+    """미션이 이어서 말할 자리면 LLM reply 를 비운 intent 를, 아니면 그대로 돌려준다."""
+    if getattr(intent, "safety_flag", "") == "emergency" or not intent.reply:
+        return intent
+    if (intent.intent == "unknown" and intent.reply != WAKE_GREETING
+            and mission_is_asking(dialog_state, last_robot_text, last_robot_age_sec)):
+        return intent.model_copy(update={"reply": ""})
+    if (intent.intent == "navigate" and intent.need_confirm
+            and dialog_state in APPROACH_ANSWER_STATES):
+        return intent.model_copy(update={"reply": ""})
+    return intent
diff --git a/src/ros_node.py b/src/ros_node.py
index 0da6f2c..392f7de 100644
--- a/src/ros_node.py
+++ b/src/ros_node.py
@@ -42,6 +42,7 @@ from .langchain_intent_parser import (
     parse_intent, parse_intent_audio)
 from .ledger_view import render_ledger
 from .mission_phrases import WAIT_BEACON
+from .mission_question import quiet_for_mission
 from .llm_backend import BackendState, parse_goal_event
 from .realtime_intent import audio_turn_applies, get_realtime_client, pcm16_from_audio_msg
 from .situation_board import SituationBoard, parse_goal_event_name
@@ -380,6 +381,15 @@ class LlmIntentNode(Node):
         if self._local and not llm_first:
             intent = self._apply_misheard_rule(intent, text)
 
+        # 2-3) 미션이 질문 중이면 못 알아들은 답에 LLM 은 말하지 않는다 — 미션이 같은 질문을
+        #      한 번 다시 한다. 접근 질문·돌아서기 중 목적지 답의 확인 질문도 미션 몫이다
+        #      (2026-10-08 미션 요청 반응표). 판단은 순수 함수(mission_question)가 한다.
+        last_t, last_text = self._robot_recent[-1] if self._robot_recent else (0.0, "")
+        quieted = quiet_for_mission(intent, self._robot_state.dialog_state, last_text,
+                                    time.time() - last_t)
+        silenced = quieted is not intent
+        intent = quieted
+
         # 3) VicaIntent 를 커스텀 메시지로 발행한다 (이동 명령이 아니라 '제안').
         #    resume 제안만 확인 응답("네")까지 보류한다 — should_forward_intent.
         if should_forward_intent(intent):
@@ -408,7 +418,9 @@ class LlmIntentNode(Node):
         # 4) 대화 히스토리를 갱신한다 (다음 발화가 맥락을 기억하도록).
         #    소리 모드에서는 로봇 줄(AI)을 여기서 넣지 않는다 — 실제로 소리 난 말이
         #    /vica/tts_done 으로 들어와 _on_tts_done_text 가 넣는다(미션의 질문 포함).
-        if self._spoken_history:
+        if self._spoken_history or silenced:
+            # 2-3 에서 지운 대답은 기록에 빈 줄로 남기지 않는다 — 물어 둔 질문이 마지막 로봇
+            # 말로 남아야 다음 "네"가 그 질문의 답이 된다.
             self._history.extend([HumanMessage(text)])
         else:
             self._history.extend([HumanMessage(text), AIMessage(intent.reply)])
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `763 passed` 

- [ ] **Step 5: 음성 노드가 ROS 환경에서 불러와지는지 본다** (`ros_node`는 시험이 없다)

```bash
(source /opt/ros/humble/setup.bash && source vica_ros2_ws/install/setup.bash
 cd vica-voice-llm && .venv/bin/python -c "import src.ros_node; print('ok')")
```
Expected: `ok`

- [ ] **Step 6: 커밋한다** (push 하지 않는다)

```bash
git -C vica-voice-llm add tests/test_mission_reactions_voice.py src/mission_phrases.py src/mission_question.py src/ros_node.py
git -C vica-voice-llm commit -m "feat(voice): 미션이 질문 중이면 못 알아들은 답에 LLM 이 말하지 않는다 — 다시 묻기는 미션이(목소리 하나)" -m "$VICA_TRAILER"
```


### Task 15: 음성 — "네, XX로 안내해드릴까요?"도 확인 질문, 취소 확인의 아니요는 미션으로

결정 4의 짝: `_question_destination`이 "네, " + 확인 질문도 그 목적지의 확인 질문으로 본다(못 알아보면
로컬·확인 중 경로가 앞서 물은 목적지로 "응"을 붙인다). 작업 7의 짝: "안내를 취소할까요?"에 짧은 "아니요"는
`deny`(reply "")로 넘긴다 — 미션이 "안내를 계속하겠습니다."라고 답한다. 예전 `COMMAND_DECLINED`("알겠습니다.
계속 진행할게요.")는 음성이 쥔 "다시 출발할까요?"의 아니요에만 남는다. 기존 시험 1개(`test_no_after_cancel_question_continues`)를 새 동작으로 고친다.

**Files:**
- Modify: `vica-voice-llm/tests/test_command_intents.py`
- Modify: `vica-voice-llm/tests/test_mission_reactions_voice.py`
- Modify: `vica-voice-llm/src/langchain_intent_parser.py`
- Modify: `vica-voice-llm/src/mission_phrases.py`

**Interfaces:**
- Produces: `mission_phrases.CONFIRM_SWITCH = "네, {prompt}"`(미션 `MSG_CONFIRM_SWITCH` 사본)

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/15-test.patch"
```

<details><summary>15-test.patch (65줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_command_intents.py b/tests/test_command_intents.py
index bb36572..d2da024 100644
--- a/tests/test_command_intents.py
+++ b/tests/test_command_intents.py
@@ -45,12 +45,20 @@ class TestCommandConfirmFlow:
         assert result.intent == "cancel"
         assert result.need_confirm is False
 
-    def test_no_after_cancel_question_continues(self):
+    def test_no_after_cancel_question_goes_to_the_mission(self):
+        """취소 확인의 "아니요"는 미션이 받아 "안내를 계속하겠습니다."라고 답한다(2026-10-08)."""
         history = [HumanMessage("취소해줘"), AIMessage(CANCEL_CONFIRM)]
         result = parse_intent("아니요", [DEST], history=history)
+        assert result.intent == "deny"
+        assert result.reply == ""
+        assert result.need_confirm is False
+
+    def test_no_after_resume_question_is_still_answered_here(self):
+        """"다시 출발할까요?"는 음성이 쥔 질문이라 미션이 모른다 — 대답은 지금처럼 여기서."""
+        history = [AIMessage(RESUME_CONFIRM)]
+        result = parse_intent("아니요", [DEST], history=history)
         assert result.intent == "unknown"
         assert result.reply == COMMAND_DECLINED
-        assert result.need_confirm is False
 
     def test_yes_after_resume_question_confirms(self):
         history = [AIMessage(RESUME_CONFIRM)]
diff --git a/tests/test_mission_reactions_voice.py b/tests/test_mission_reactions_voice.py
index f5153fa..277e05e 100644
--- a/tests/test_mission_reactions_voice.py
+++ b/tests/test_mission_reactions_voice.py
@@ -5,7 +5,9 @@
 from src import langchain_intent_parser as parser
 from src import local_rules
 from src.langchain_intent_parser import _build_system_prompt
-from src.mission_phrases import WAIT_FINISH_ASK, WAIT_NEED_ASK
+from langchain_core.messages import AIMessage, HumanMessage
+
+from src.mission_phrases import CONFIRM_SWITCH, WAIT_FINISH_ASK, WAIT_NEED_ASK
 from src.mission_question import mission_is_asking, quiet_for_mission
 from src.replies import CANCEL_CONFIRM, RETRY_PROMPT, WAKE_GREETING
 from src.schema import DestinationData, VicaIntent
@@ -85,3 +87,22 @@ class TestQuietForMission:
         kept = quiet_for_mission(_i("navigate", "화장실로 안내해드릴까요?", need_confirm=True),
                                  "idle", "", 1.0)
         assert kept.reply == "화장실로 안내해드릴까요?"
+
+
+# ---- Task 15: "네, XX로 안내해드릴까요?"도 확인 질문이다 -----------------------------
+ELEV = DestinationData(id="elev", name="엘리베이터", confirm_prompt="엘리베이터로 안내해드릴까요?")
+
+
+def test_switch_question_points_at_the_new_destination():
+    history = [AIMessage(DEST.confirm_prompt), HumanMessage("아니 엘리베이터로 가자"),
+               AIMessage(CONFIRM_SWITCH.format(prompt=ELEV.confirm_prompt))]
+    assert parser._pending_confirm_destination(history, [DEST, ELEV]) is ELEV
+    assert parser._recent_confirm_destination(history, [DEST, ELEV]) is ELEV
+
+
+def test_yes_to_the_switch_question_confirms_the_new_destination():
+    history = [AIMessage(DEST.confirm_prompt), HumanMessage("아니 엘리베이터로 가자"),
+               AIMessage(CONFIRM_SWITCH.format(prompt=ELEV.confirm_prompt))]
+    result = parser._shortcut_intent("응", history, [DEST, ELEV])
+    assert result is not None and result.intent == "navigate"
+    assert result.matched_destination_id == "elev"
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `tests/test_mission_reactions_voice.py` 수집 오류 — `ImportError: cannot import name 'CONFIRM_SWITCH'`. 결과 줄: `a445c/scratchpad/proto/wt/tmpiyhthkx0/vica-voice-llm/src/mission_phrases.py)
=========================== short test summary info ============================
ERROR tests/test_mission_reactions_voice.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/15-code.patch"
```

<details><summary>15-code.patch (48줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/langchain_intent_parser.py b/src/langchain_intent_parser.py
index 3b87ecc..445ea26 100644
--- a/src/langchain_intent_parser.py
+++ b/src/langchain_intent_parser.py
@@ -16,6 +16,7 @@ from pydantic import BaseModel, Field, ValidationError
 
 from .destination_loader import _josa_euro
 from .destination_matcher import match_destination
+from .mission_phrases import CONFIRM_SWITCH
 from .handle_mode import (
     AFFIRMATIVES, NEGATIVES, SOFT_AFFIRMATIVES, normalize_short_reply)
 from . import local_rules
@@ -268,7 +269,10 @@ def _question_destination(text: str, destinations: Sequence[DestinationData]):
     if not text:
         return None
     for dest in destinations:
-        if dest.confirm_prompt and dest.confirm_prompt == text:
+        # 미션이 확인 질문 중 다른 목적지로 다시 묻는 "네, XX로 안내해드릴까요?"(2026-10-08 결정
+        # 4)도 그 목적지의 확인 질문이다 — 못 알아보면 "응"이 앞서 물은 곳으로 붙는다.
+        if dest.confirm_prompt and text in (
+                dest.confirm_prompt, CONFIRM_SWITCH.format(prompt=dest.confirm_prompt)):
             return dest
     # 이름이 다른 이름의 끝과 겹치면("화장실"·"남자 화장실") 긴 쪽이 맞다.
     matches = [
@@ -601,6 +605,10 @@ def _shortcut_intent(user_text: str, history: Optional[list[BaseMessage]],
                 need_confirm=False,
             )
         if word in _NEGATIVES:
+            if pending_command == "cancel":
+                # "안내를 취소할까요?"에 아니요 — 미션이 받고 "안내를 계속하겠습니다."라고
+                # 답한다(2026-10-08 반응표). 여기서 따로 말하면 두 목소리다.
+                return VicaIntent(intent="deny", confidence=1.0, reply="", need_confirm=False)
             return VicaIntent(
                 intent="unknown",
                 confidence=1.0,
diff --git a/src/mission_phrases.py b/src/mission_phrases.py
index 5a679dc..6d7dc95 100644
--- a/src/mission_phrases.py
+++ b/src/mission_phrases.py
@@ -43,6 +43,8 @@ ESTOP_WAKE = "지금은 비상 멈춤 상태입니다."
 # ---- 미션 요청 반응표 (2026-10-08) --------------------------------------------------
 # 대기 중 "취소" — 안내를 끝낼지 묻는다(사용자 결정 3, 사용자 문구).
 WAIT_NEED_ASK = "안내가 필요 없으신가요?"
+# 확인 질문 중 다른 목적지를 확정하면 "네, " + 그 목적지의 확인 질문(사용자 결정 4).
+CONFIRM_SWITCH = "네, {prompt}"
 
 # 숫자로 끝나는 이름을 읽을 때 마지막 숫자의 받침(영·일·삼·육·칠·팔 있음, 이·사·오·구 없음).
 _DIGIT_HAS_BATCHIM = {
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `766 passed` 

- [ ] **Step 5: 커밋한다** (push 하지 않는다)

```bash
git -C vica-voice-llm add tests/test_command_intents.py tests/test_mission_reactions_voice.py src/langchain_intent_parser.py src/mission_phrases.py
git -C vica-voice-llm commit -m "fix(voice): '네, XX로 안내해드릴까요?'도 확인 질문으로 보고, 취소 확인의 아니요는 미션으로 넘긴다" -m "$VICA_TRAILER"
```


### Task 16: 음성 — 음성이 쥔 "다시 출발할까요?"를 한 번 다시 묻는다

다시 묻기 표의 "다시 출발 확인" 행. 미션은 이 질문을 모르므로(확인 전 resume 은 음성이 쥔다) 음성이
한다. 못 알아들은 답(unknown)이면 `_publish_intent` 맨 앞에서 같은 질문(확인 전 resume)으로 바꾼다 — 재청취
기각보다 먼저여야 한다. 듣기 창이 빈손으로 닫히면(`/vica/listen_state`가 empty…) 한 번 다시 묻는다. 기록에
그 질문이 두 번 연달아 있으면 이미 다시 물은 것이다 — 그 뒤는 선 채로.

**Files:**
- Modify: `vica-voice-llm/tests/test_mission_reactions_voice.py`
- Modify: `vica-voice-llm/src/mission_question.py`
- Modify: `vica-voice-llm/src/ros_node.py`

**Interfaces:**
- Produces: `resume_reasked(history) -> bool`, `reask_held_resume(intent, history) -> VicaIntent`, `should_reask_resume_on_silence(history) -> bool`; 노드 구독 `/vica/listen_state` → `_on_listen_state_for_resume`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/16-test.patch"
```

<details><summary>16-test.patch (47줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_mission_reactions_voice.py b/tests/test_mission_reactions_voice.py
index 277e05e..41f13c5 100644
--- a/tests/test_mission_reactions_voice.py
+++ b/tests/test_mission_reactions_voice.py
@@ -8,8 +8,10 @@ from src.langchain_intent_parser import _build_system_prompt
 from langchain_core.messages import AIMessage, HumanMessage
 
 from src.mission_phrases import CONFIRM_SWITCH, WAIT_FINISH_ASK, WAIT_NEED_ASK
-from src.mission_question import mission_is_asking, quiet_for_mission
-from src.replies import CANCEL_CONFIRM, RETRY_PROMPT, WAKE_GREETING
+from src.mission_question import (mission_is_asking, quiet_for_mission, reask_held_resume,
+                                  resume_reasked, should_reask_resume_on_silence)
+from src.replies import CANCEL_CONFIRM, RESUME_CONFIRM, RETRY_PROMPT, WAKE_GREETING
+from src.schema import should_forward_intent
 from src.schema import DestinationData, VicaIntent
 
 DEST = DestinationData(id="wc", name="화장실", confirm_prompt="화장실로 안내해드릴까요?")
@@ -106,3 +108,29 @@ def test_yes_to_the_switch_question_confirms_the_new_destination():
     result = parser._shortcut_intent("응", history, [DEST, ELEV])
     assert result is not None and result.intent == "navigate"
     assert result.matched_destination_id == "elev"
+
+
+# ---- Task 16: 음성이 쥔 "다시 출발할까요?" 다시 묻기 ----------------------------------
+class TestHeldResumeReask:
+    def test_strange_answer_reasks_once(self):
+        history = [HumanMessage("가자?"), AIMessage(RESUME_CONFIRM), HumanMessage("음냐")]
+        out = reask_held_resume(_i("unknown", ""), history)
+        assert (out.intent, out.need_confirm, out.reply) == ("resume", True, RESUME_CONFIRM)
+        assert not should_forward_intent(out)          # 미션에는 안 간다 — 말만 나간다
+
+    def test_second_strange_answer_is_left_alone(self):
+        history = [AIMessage(RESUME_CONFIRM), HumanMessage("음냐"), AIMessage(RESUME_CONFIRM),
+                   HumanMessage("음냐")]
+        assert resume_reasked(history)
+        out = reask_held_resume(_i("unknown", ""), history)
+        assert out.intent == "unknown"
+
+    def test_other_questions_are_not_touched(self):
+        history = [AIMessage(CANCEL_CONFIRM)]
+        assert reask_held_resume(_i("unknown", ""), history).intent == "unknown"
+
+    def test_silence_reasks_once(self):
+        assert should_reask_resume_on_silence([AIMessage(RESUME_CONFIRM)])
+        assert not should_reask_resume_on_silence(
+            [AIMessage(RESUME_CONFIRM), HumanMessage("음냐"), AIMessage(RESUME_CONFIRM)])
+        assert not should_reask_resume_on_silence([AIMessage(RESUME_CONFIRM), HumanMessage("네")])
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `tests/test_mission_reactions_voice.py` 수집 오류 — `ImportError: cannot import name 'reask_held_resume'`. 결과 줄: `45c/scratchpad/proto/wt/tmp_vqwetx2/vica-voice-llm/src/mission_question.py)
=========================== short test summary info ============================
ERROR tests/test_mission_reactions_voice.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error`

- [ ] **Step 3: 구현한다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/16-code.patch"
```

<details><summary>16-code.patch (118줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/mission_question.py b/src/mission_question.py
index 91ee3ed..d489254 100644
--- a/src/mission_question.py
+++ b/src/mission_question.py
@@ -8,9 +8,12 @@ ros_node 는 rclpy 없이 시험할 수 없어 판단은 여기 순수 함수로
 """
 from __future__ import annotations
 
+from langchain_core.messages import AIMessage, BaseMessage
+
 from .local_rules import ANSWER_WAIT_STATES
 from .mission_phrases import WAIT_FINISH_ASK, WAIT_NEED_ASK
-from .replies import CANCEL_CONFIRM, WAKE_GREETING
+from .replies import CANCEL_CONFIRM, RESUME_CONFIRM, WAKE_GREETING
+from .schema import VicaIntent
 
 # 대기 중·주행 중에도 미션이 묻는 질문 — dialog_state 만으로는 질문 중인지 모른다.
 MISSION_QUESTIONS = frozenset({WAIT_FINISH_ASK, WAIT_NEED_ASK, CANCEL_CONFIRM})
@@ -40,3 +43,35 @@ def quiet_for_mission(intent, dialog_state: str, last_robot_text: str,
             and dialog_state in APPROACH_ANSWER_STATES):
         return intent.model_copy(update={"reply": ""})
     return intent
+
+
+# ---- 음성이 쥔 "다시 출발할까요?" 다시 묻기 (2026-10-08) -------------------------------
+# 미션은 이 질문을 모른다(schema.should_forward_intent 가 확인 전 resume 을 쥔다). 그래서
+# 다시 묻기도 음성이 한다 — 못 알아들은 답이나 빈손으로 닫힌 듣기 창에 한 번만.
+def _robot_lines(history: list[BaseMessage]) -> list[str]:
+    return [m.content for m in history if isinstance(m, AIMessage)]
+
+
+def resume_reasked(history: list[BaseMessage]) -> bool:
+    """이미 한 번 다시 물었나 — 로봇 말 마지막 두 줄이 모두 "다시 출발할까요?"."""
+    lines = _robot_lines(history or [])
+    return len(lines) >= 2 and lines[-1] == RESUME_CONFIRM and lines[-2] == RESUME_CONFIRM
+
+
+def reask_held_resume(intent, history: list[BaseMessage]):
+    """"다시 출발할까요?"에 못 알아들은 답(unknown)이면 같은 질문을 한 번 다시 묻는 intent 로
+    바꾼다. 확인 전 resume 이라 미션에는 가지 않고 말만 나간다. 그 밖에는 그대로."""
+    if intent.intent != "unknown" or getattr(intent, "safety_flag", "") == "emergency":
+        return intent
+    lines = _robot_lines(history or [])
+    if not lines or lines[-1] != RESUME_CONFIRM or resume_reasked(history):
+        return intent
+    return VicaIntent(intent="resume", confidence=1.0, reply=RESUME_CONFIRM, need_confirm=True)
+
+
+def should_reask_resume_on_silence(history: list[BaseMessage]) -> bool:
+    """듣기 창이 빈손으로 닫혔을 때 "다시 출발할까요?"를 한 번 다시 물을까. 질문 뒤 사용자
+    말이 없었고(마지막 줄이 그 질문) 아직 다시 묻지 않았을 때만."""
+    if not history or not isinstance(history[-1], AIMessage):
+        return False
+    return history[-1].content == RESUME_CONFIRM and not resume_reasked(history)
diff --git a/src/ros_node.py b/src/ros_node.py
index 392f7de..1c8c24a 100644
--- a/src/ros_node.py
+++ b/src/ros_node.py
@@ -42,15 +42,17 @@ from .langchain_intent_parser import (
     parse_intent, parse_intent_audio)
 from .ledger_view import render_ledger
 from .mission_phrases import WAIT_BEACON
-from .mission_question import quiet_for_mission
+from .mission_question import (quiet_for_mission, reask_held_resume,
+                               should_reask_resume_on_silence)
 from .llm_backend import BackendState, parse_goal_event
 from .realtime_intent import audio_turn_applies, get_realtime_client, pcm16_from_audio_msg
 from .situation_board import SituationBoard, parse_goal_event_name
-from .replies import COMMAND_DECLINED, LLM_UNAVAILABLE, RETRY_PROMPT, WAKE_GREETING, expects_answer
+from .replies import (COMMAND_DECLINED, LLM_UNAVAILABLE, RESUME_CONFIRM, RETRY_PROMPT,
+                      WAKE_GREETING, expects_answer)
 from .ros_convert import intent_to_msg, msg_to_robot_state
 from .schema import should_forward_intent, RobotState, VicaIntent
 from .stt_guard import is_hallucination  # noqa: F401  (텍스트 경로 관문용, 소리 모드는 안 쓴다)
-from .tts_queue import request_for_intent
+from .tts_queue import RESPONSE, build_request, request_for_intent
 
 
 # 재청취 창 문맥으로 보는 시간. 질문 발화(수 초) + 청취 창 + 답 처리까지
@@ -150,6 +152,8 @@ class LlmIntentNode(Node):
         # (2026-08-31 야간 실기). "비카야" 직접 호출은 대답할 자격을 되살린다.
         self._followup_until = 0.0
         self.create_subscription(Bool, "/vica/listen_request", self._on_listen_request, 10)
+        # 듣기 창이 빈손으로 닫혔다 — 음성이 쥔 "다시 출발할까요?"를 한 번 다시 묻는다(2026-10-08).
+        self.create_subscription(String, "/vica/listen_state", self._on_listen_state_for_resume, 10)
         self.create_subscription(String, "/vica/wake", self._on_wake_signal, 10)
 
         # ----- 클라우드→로컬 자동 전환 (2026-09-19 설계) ------------------------
@@ -352,6 +356,9 @@ class LlmIntentNode(Node):
         llm_first(소리 모드 모델 전결): 재청취 기각을 하지 않는다 — 대꾸할지 침묵할지
         (reply 가 빈 문자열)는 모델이 정했다.
         """
+        # 2-0) 음성이 쥔 "다시 출발할까요?"에 못 알아들은 답 — 같은 질문을 한 번 다시 묻는다
+        #      (2026-10-08 다시 묻기). 아래 재청취 기각보다 먼저다 — 기각되면 아무도 안 묻는다.
+        intent = reask_held_resume(intent, self._history.messages)
         # 2-1) 재청취 창의 무의미 발화는 침묵으로 버린다 — 대꾸도, 기록도
         #      하지 않는다 (멘트 최소주의: 실패·경계는 로그. 못 들은 질문의
         #      재질문은 미션이 유일한 목소리다). 히스토리에 안 남기는 것이
@@ -425,6 +432,19 @@ class LlmIntentNode(Node):
         else:
             self._history.extend([HumanMessage(text), AIMessage(intent.reply)])
 
+    def _on_listen_state_for_resume(self, msg: String) -> None:
+        """듣기 창이 빈손으로 닫혔다. 마지막 로봇 말이 음성이 쥔 "다시 출발할까요?"이고 아직
+        다시 묻지 않았으면 한 번 더 묻는다(2026-10-08 다시 묻기). 그래도 없으면 선 채로 둔다."""
+        if not (msg.data or "").startswith("empty"):
+            return
+        if not should_reask_resume_on_silence(self._history.messages):
+            return
+        self.get_logger().info("다시 출발 확인 — 대답이 없어 한 번 다시 묻는다")
+        self._tts_pub.publish(String(data=build_request(RESPONSE, RESUME_CONFIRM)))
+        self._listen_pub.publish(Bool(data=True))
+        if not self._spoken_history:
+            self._history.extend([AIMessage(RESUME_CONFIRM)])
+
     def _apply_misheard_rule(self, intent: VicaIntent, text: str) -> VicaIntent:
         """로컬 규칙: 창 밖 못 알아들은 말의 대꾸를 고정 문구 한 번 → 침묵으로 바꾼다."""
         fixed = {WAKE_GREETING, COMMAND_DECLINED, LLM_UNAVAILABLE}
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `770 passed` 

- [ ] **Step 5: 음성 노드가 ROS 환경에서 불러와지는지 본다** (`ros_node`는 시험이 없다)

```bash
(source /opt/ros/humble/setup.bash && source vica_ros2_ws/install/setup.bash
 cd vica-voice-llm && .venv/bin/python -c "import src.ros_node; print('ok')")
```
Expected: `ok`

- [ ] **Step 6: 커밋한다** (push 하지 않는다)

```bash
git -C vica-voice-llm add tests/test_mission_reactions_voice.py src/mission_question.py src/ros_node.py
git -C vica-voice-llm commit -m "feat(voice): 음성이 쥔 '다시 출발할까요?'를 한 번 다시 묻는다 — 못 알아들음·빈손 창(다시 묻기)" -m "$VICA_TRAILER"
```


### Task 17: 음성 — 새 문장 목록과 굽기

새 문장(사용자 승인) "안내가 필요 없으신가요?"와 '입구 앞' M2·M2′ 6문장(기존 틀 + 기존 장소 말)을 굽는
목록(`baked_mission_ments`)에 넣고, 목적지마다 "네, XX로 안내해드릴까요?"를 미리 합성 목록
(`standalone_prewarm`)에 넣는다. 미션 상수와 글자가 같은지 계약 시험을 더한다.

굽기는 사용자가 한다 — **로봇 스택을 모두 내린 상태에서만**(CosyVoice 약 3 GB). 굽기 전에는 `TestBaked`가
실패하는 것이 정상이다(새 문장이 아직 manifest 에 없다).

**Files:**
- Modify: `vica-voice-llm/tests/test_mission_phrases.py`
- Modify: `vica-voice-llm/src/mission_phrases.py`

**Interfaces:**
- Produces: `mission_phrases.WAIT_PLACE_AT_DESTINATION`, `wait_front_sentences() -> dict[str, str]`

- [ ] **Step 1: 시험을 먼저 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/17-test.patch"
```

<details><summary>17-test.patch (32줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_mission_phrases.py b/tests/test_mission_phrases.py
index 8df33f6..d267f24 100644
--- a/tests/test_mission_phrases.py
+++ b/tests/test_mission_phrases.py
@@ -81,6 +81,27 @@ class TestSentences:
         assert _fill_defaults(dest).confirm_prompt == ml.say_destination(
             ml.MSG_CONFIRM_PROMPT_FALLBACK, "식당")
 
+    def test_mission_reaction_sentences(self, ml):
+        """미션 요청 반응표(2026-10-08) 새 문장·장소 말이 미션과 같은 글자다."""
+        assert mp.WAIT_NEED_ASK == ml.MSG_WAIT_NEED_ASK
+        assert mp.CONFIRM_SWITCH == ml.MSG_CONFIRM_SWITCH
+        assert mp.WAIT_PLACE_AT_DESTINATION == ml.WAIT_PLACE_AT_DESTINATION
+        # 안내 주행 중 "다시 가자"의 답 — 음성 replies.ALREADY_GOING 과 같은 글자.
+        for name in ("409호", "식당", "화장실"):
+            assert ml.say_destination(ml.MSG_ALREADY_GOING, name) == replies.ALREADY_GOING.format(
+                cur=name, cur_josa=_josa_euro(name))
+
+    def test_front_sentences_match_mission_formatting(self, ml):
+        mission = {ml.MSG_WAIT_SPOT_CONFIRM.format(minutes=m, place=ml.WAIT_PLACE_AT_DESTINATION)
+                   for m in mp.BAKED_WAIT_MINUTES}
+        mission.add(ml.MSG_WAIT_SPOT_DEFAULT.format(place=ml.WAIT_PLACE_AT_DESTINATION))
+        assert set(mp.wait_front_sentences().values()) == mission
+        assert len(mission) == 6
+
+    def test_switch_question_is_prewarmed(self):
+        dests = [DestinationData(id="x", name="식당", confirm_prompt="식당으로 안내해드릴까요?")]
+        assert "네, 식당으로 안내해드릴까요?" in mp.standalone_prewarm(dests)
+
     def test_door_side_words_cover_every_mission_answer(self, ml):
         seen = {ml.door_side_word(door, robot)
                 for door in range(0, 360, 5) for robot in range(0, 360, 7)}
```

</details>

- [ ] **Step 2: 시험이 실패하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: 새 계약 시험 3개가 실패한다. 결과 줄: `3 failed, 770 passed`

- [ ] **Step 3: 구현한다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/17-code.patch"
```

<details><summary>17-code.patch (60줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/mission_phrases.py b/src/mission_phrases.py
index 6d7dc95..faf8198 100644
--- a/src/mission_phrases.py
+++ b/src/mission_phrases.py
@@ -45,6 +45,9 @@ ESTOP_WAKE = "지금은 비상 멈춤 상태입니다."
 WAIT_NEED_ASK = "안내가 필요 없으신가요?"
 # 확인 질문 중 다른 목적지를 확정하면 "네, " + 그 목적지의 확인 질문(사용자 결정 4).
 CONFIRM_SWITCH = "네, {prompt}"
+# 대기 장소가 없는 목적지로 돌아가 기다릴 때(홈 가는 중 "기다려", 결정 1)의 장소 말 — 미션
+# WAIT_PLACE_AT_DESTINATION. 대기 장소가 막혔을 때(M6 뒤) 상황판의 말과 같다.
+WAIT_PLACE_AT_DESTINATION = "입구 앞"
 
 # 숫자로 끝나는 이름을 읽을 때 마지막 숫자의 받침(영·일·삼·육·칠·팔 있음, 이·사·오·구 없음).
 _DIGIT_HAS_BATCHIM = {
@@ -87,6 +90,18 @@ def wait_spot_sentences() -> dict[str, str]:
     return out
 
 
+def wait_front_sentences() -> dict[str, str]:
+    """구워 둘 '입구 앞' M2·M2′ 6문장(2026-10-08 결정 1). 파일 이름 → 문장."""
+    out = {
+        f"mission_msg_wait_front_{minutes}": WAIT_SPOT_CONFIRM.format(
+            minutes=minutes, place=WAIT_PLACE_AT_DESTINATION)
+        for minutes in BAKED_WAIT_MINUTES
+    }
+    out["mission_msg_wait_front_default"] = WAIT_SPOT_DEFAULT.format(
+        place=WAIT_PLACE_AT_DESTINATION)
+    return out
+
+
 def baked_mission_ments() -> dict[str, str]:
     """이번 작업에서 녹음으로 굽는 미션 문장 전부(작업 계획 탭 '소리 준비').
 
@@ -100,8 +115,11 @@ def baked_mission_ments() -> dict[str, str]:
         "mission_msg_wait_expired": WAIT_EXPIRED,
         "mission_msg_estop_wake": ESTOP_WAKE,
         "mission_msg_wait_finish_ask": WAIT_FINISH_ASK,
+        # 미션 요청 반응표(2026-10-08) — 대기 중 "취소"의 질문(결정 3).
+        "mission_msg_wait_need_ask": WAIT_NEED_ASK,
     }
     out.update(wait_spot_sentences())
+    out.update(wait_front_sentences())
     return out
 
 
@@ -111,8 +129,12 @@ def _unique(phrases: Iterable[str]) -> list[str]:
 
 
 def standalone_prewarm(destinations: Iterable) -> list[str]:
-    """혼자 말해지는 문장 — 목적지 확인 질문. 통문장이 구워져 있으면 미리 합성할 필요가 없다."""
-    return _unique(d.confirm_prompt for d in destinations)
+    """혼자 말해지는 문장 — 목적지 확인 질문과, 확인 질문 중 다른 목적지로 다시 묻는 "네, …"
+    (2026-10-08 결정 4). 통문장이 구워져 있으면 미리 합성할 필요가 없다."""
+    dests = list(destinations)
+    phrases = [d.confirm_prompt for d in dests]
+    phrases += [CONFIRM_SWITCH.format(prompt=d.confirm_prompt) for d in dests if d.confirm_prompt]
+    return _unique(phrases)
 
 
 def merged_prewarm(destinations: Iterable) -> list[str]:
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: `1 failed, 772 passed` (남는 1개는 `TestBaked` — 다음 단계의 굽기 전이라 정상)

- [ ] **Step 5: (사용자) 로봇 스택을 내리고 새 문장을 굽는다**

로봇 스택(음성·미션·Nav2)을 모두 내린 뒤에만 한다 — CosyVoice 가 RAM 약 3 GB 를 쓴다.

```bash
(cd vica-voice-llm && PYTHONPATH=~/CosyVoice:~/CosyVoice/third_party/Matcha-TTS    ~/venvs/cosyvoice/bin/python scripts/bake_one_cv.py --mission)
```
`--mission`은 manifest 에 없거나 글자가 다른 문장만 굽는다(새 7문장). 끝나면 소리를 들어 보고 이상한 것은 그
파일 이름으로 다시 굽는다(`scripts/bake_one_cv.py <stem> "<문장>"`).

- [ ] **Step 6: 굽기 뒤 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/test_mission_phrases.py -q -p no:cacheprovider)`
Expected: 전부 통과(`TestBaked` 포함)

- [ ] **Step 7: 커밋한다** (push 하지 않는다)

```bash
git -C vica-voice-llm add tests/test_mission_phrases.py src/mission_phrases.py
git -C vica-voice-llm add -f assets/baked/manifest.json assets/baked/mission_msg_wait_need_ask.wav 'assets/baked/mission_msg_wait_front_*.wav'
git -C vica-voice-llm commit -m "feat(voice): 반응표 새 문장 굽기 목록 — 안내가 필요 없으신가요·입구 앞 M2 6문장, 네 XX 확인 질문 미리 합성" -m "$VICA_TRAILER"
```


### Task 18 (선택 — 사용자가 새 문장을 승인한 경우에만): 접근 질문에 못 알아들은 답이면 "안내를 받으시겠어요?"만 한 번 다시

다시 묻기 표의 "접근 질문" 행. 인사까지 긴 접근 질문을 다 되풀이하지 않고 끝부분만 묻는다 — 따로 녹음할 새
문장이라 **승인 전에는 하지 않는다.** 대답이 없을 때는 다시 묻지 않는다(사람을 잘못 봤을 수 있어 남의 앞을
오래 막지 않는다 — 지금처럼 8초 뒤 "실례했습니다…" 하고 물러난다). 노드는 다시 묻기 재생이 끝나면 8초 답
시계를 다시 건다.

**Files:**
- Modify: `vica_ros2_ws/src/vica_mission_manager/test/test_reaction_rules.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_logic.py`
- Modify: `vica_ros2_ws/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py`
- Modify: `vica-voice-llm/tests/test_mission_phrases.py`
- Modify: `vica-voice-llm/src/mission_phrases.py`

**Interfaces:**
- Produces: 미션 `MSG_APPROACH_REASK = "안내를 받으시겠어요?"`, 필드 `_approach_reasked`; 음성 `mission_phrases.APPROACH_REASK`

- [ ] **Step 1: 미션 시험을 먼저 넣는다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/18m-test.patch"
```

<details><summary>18m-test.patch (28줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/test/test_reaction_rules.py b/src/vica_mission_manager/test/test_reaction_rules.py
index 25a9499..b69627f 100644
--- a/src/vica_mission_manager/test/test_reaction_rules.py
+++ b/src/vica_mission_manager/test/test_reaction_rules.py
@@ -9,6 +9,7 @@ from reaction_states import (BOUNDS, ELEV, ROOM, SPOT_DEST, asking, asking_wait_
 from vica_mission_manager.mission_logic import (
     MSG_ALREADY_GOING,
     MSG_APPROACH_ONBOARDING,
+    MSG_APPROACH_REASK,
     MSG_ASK_ENTRANCE,
     MSG_ASK_WAIT_TIME,
     MSG_CONFIRM_PROMPT_FALLBACK,
@@ -366,3 +367,15 @@ def test_llm_clarify_is_not_a_strange_answer():
     logic, t = confirming()
     assert logic.on_voice_intent(intent("clarify"), t, lookup, BOUNDS, True) == []
     assert logic.state == State.CONFIRMING
+
+
+# ---- Task 18 (승인 시): 접근 질문에 못 알아들은 답 -------------------------------------
+def test_approach_strange_answer_reasks_the_short_question_once():
+    logic, t = awaiting_user()
+    acts = logic.on_voice_intent(intent("unknown"), t, lookup, BOUNDS, True)
+    assert [(a.text, a.expects_reply) for a in acts if isinstance(a, Say)] == [
+        (MSG_APPROACH_REASK, True)]
+    assert logic.on_voice_intent(intent("unknown"), t + 3, lookup, BOUNDS, True) == []
+    logic.on_approach_question_spoken(t + 4)       # 노드가 다시 묻기 재생 끝을 알려 준다
+    logic.on_tick(t + 12.5, NavStatus.NONE)
+    assert logic.state != State.AWAITING_USER      # 그래도 답이 없으면 지금처럼 물러난다
```

</details>

- [ ] **Step 2: 실패하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `test/test_reaction_rules.py` 수집 오류 — `ImportError: cannot import name 'MSG_APPROACH_REASK'`.

- [ ] **Step 3: 미션을 구현한다**

```bash
git -C vica_ros2_ws apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/18m-code.patch"
```

<details><summary>18m-code.patch (67줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_logic.py b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
index 6bec7ae..4b99e2a 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_logic.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_logic.py
@@ -535,6 +535,9 @@ MSG_ALREADY_GOING = "지금 {name}{josa} 가는 중이에요."
 # 들려 쓰지 않는다. 구운 판(assets/baked)과 글자가 같아야 한다.
 MSG_APPROACH_COMING = "동행로봇 비카가 다가가고 있어요."
 MSG_APPROACH_QUESTION = "안녕하세요? 시각장애인 안내로봇 비카입니다. 안내를 받으시겠어요?"
+# 접근 질문에 못 알아들은 답 — 인사 없이 끝부분만 한 번 다시 묻는다(2026-10-08 다시 묻기, 새 녹음
+# 문장이라 사용자 승인 뒤에만 쓴다). 음성 mission_phrases.APPROACH_REASK 와 같은 글자.
+MSG_APPROACH_REASK = "안내를 받으시겠어요?"
 MSG_APPROACH_ACCEPTED = "네, 잠시만 기다려주세요. 로봇이 회전하니 주의하세요."
 MSG_APPROACH_DECLINED = "알겠습니다. 이만 물러납니다."
 MSG_APPROACH_ONBOARDING = "저에게 말을 거실 때는 '비카야'라고 불러주세요. 어디로 가고 싶으신가요?"
@@ -1416,6 +1419,7 @@ class MissionLogic:
         # 접근 질문·돌아서기 중에 사용자가 말한 목적지(2026-10-08 반응표). 손잡이를 내준 뒤
         # 온보딩 대신 이 목적지로 확인 질문을 한다. 그때 쓰고 비운다.
         self._approach_dest: Optional[Destination] = None
+        self._approach_reasked = False   # 접근 질문을 이미 다시 물었나(2026-10-08)
         # 지금 확인 질문의 문장(2026-10-08 반응표). "다시 가자"·다시 묻기에서 같은 질문을 한다.
         self._confirm_prompt = ""
         # 다시 묻기(2026-10-08): 확인 질문·취소 확인을 다시 물을 시각과 이미 다시 물었는지.
@@ -1805,6 +1809,15 @@ class MissionLogic:
             return self.on_approach_answer(True, now)
         if intent.intent == "cancel":
             return self.on_approach_answer(False, now)
+        if intent.intent == "unknown":
+            # 못 알아들은 답 — "안내를 받으시겠어요?"만 한 번 다시 묻는다. 답 시계는 그 말이 끝난
+            # 뒤 노드가 on_approach_question_spoken 으로 다시 건다. 대답이 없을 때는 다시 묻지
+            # 않는다 — 사람을 잘못 봤을 수 있어 앞을 오래 막지 않는다(2026-10-08 다시 묻기).
+            if self._approach_reasked:
+                return []
+            self._approach_reasked = True
+            self._response_deadline = now + APPROACH_QUESTION_STUCK_SEC
+            return [self._ask(MSG_APPROACH_REASK)]
         if intent.intent in ("pause", "resume"):
             self._response_deadline = now + self.approach_response_timeout_sec
             return [self._ask(MSG_WAKE_GREETING)]
@@ -2853,6 +2866,7 @@ class MissionLogic:
         호출 전후로 각자 정한다 — 여기서는 다루지 않는다.
         """
         self.state = State.AWAITING_USER
+        self._approach_reasked = False
         # 여기서는 탈출용 안전망만 건다. 진짜 응답 8초는 질문 재생이 끝난
         # 시점(on_approach_question_spoken)부터 — 도착 후 대화와 같은 방식.
         # 큐 시각 기준 8초는 창이 0초가 되는 결함이었다.
diff --git a/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py b/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
index c408ff0..c7c1812 100644
--- a/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
+++ b/src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
@@ -69,6 +69,7 @@ from .mission_logic import (
     Haptic,
     MSG_APPROACH_ONBOARDING,
     MSG_APPROACH_QUESTION,
+    MSG_APPROACH_REASK,
     MSG_DEST_RETRY,
     NEAR_CALL_MAX_M,
     NEAR_CALL_NO_SPIN_M,
@@ -691,7 +692,7 @@ class MissionManagerNode(Node):
         다른 멘트(수락·도착 등)의 재생 완료는 응답 대기와 무관하고, 로직 쪽이
         AWAITING_USER 가 아니면 무시하므로 이중 방어다.
         """
-        if MSG_APPROACH_QUESTION in msg.data:
+        if MSG_APPROACH_QUESTION in msg.data or msg.data.strip() == MSG_APPROACH_REASK:
             self.logic.on_approach_question_spoken(self._now())
         # 손잡이 힌트는 재생 완료를 기다리지 않는다 — 진동이 힌트와 같은 순간
         # 시작해 잡을 때까지 이어진다(2026-09-30, 09-11 I-2 장치 폐기).
```

</details>

- [ ] **Step 4: 통과하는지 본다**

Run: `(cd vica_ros2_ws/src/vica_mission_manager && python3 -m pytest test/ -q -p no:cacheprovider)`
Expected: `3 failed, 983 passed, 1 skipped` (실패 3개는 원래 실패)

- [ ] **Step 5: 음성 시험을 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/18v-test.patch"
```

<details><summary>18v-test.patch (13줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/tests/test_mission_phrases.py b/tests/test_mission_phrases.py
index d267f24..28757a2 100644
--- a/tests/test_mission_phrases.py
+++ b/tests/test_mission_phrases.py
@@ -86,6 +86,8 @@ class TestSentences:
         assert mp.WAIT_NEED_ASK == ml.MSG_WAIT_NEED_ASK
         assert mp.CONFIRM_SWITCH == ml.MSG_CONFIRM_SWITCH
         assert mp.WAIT_PLACE_AT_DESTINATION == ml.WAIT_PLACE_AT_DESTINATION
+        assert mp.APPROACH_REASK == ml.MSG_APPROACH_REASK
+        assert replies.APPROACH_QUESTION.endswith(mp.APPROACH_REASK)
         # 안내 주행 중 "다시 가자"의 답 — 음성 replies.ALREADY_GOING 과 같은 글자.
         for name in ("409호", "식당", "화장실"):
             assert ml.say_destination(ml.MSG_ALREADY_GOING, name) == replies.ALREADY_GOING.format(
```

</details>

- [ ] **Step 6: 음성 문장 목록에 넣는다**

```bash
git -C vica-voice-llm apply "$PWD/docs/superpowers/plans/2026-10-08-mission-request-reactions/18v-code.patch"
```

<details><summary>18v-code.patch (21줄) — 이 패치가 하는 일 그대로</summary>

```diff
diff --git a/src/mission_phrases.py b/src/mission_phrases.py
index faf8198..8004ec6 100644
--- a/src/mission_phrases.py
+++ b/src/mission_phrases.py
@@ -48,6 +48,8 @@ CONFIRM_SWITCH = "네, {prompt}"
 # 대기 장소가 없는 목적지로 돌아가 기다릴 때(홈 가는 중 "기다려", 결정 1)의 장소 말 — 미션
 # WAIT_PLACE_AT_DESTINATION. 대기 장소가 막혔을 때(M6 뒤) 상황판의 말과 같다.
 WAIT_PLACE_AT_DESTINATION = "입구 앞"
+# 접근 질문에 못 알아들은 답 — 끝부분만 한 번 다시(사용자 승인 뒤에만 쓴다, 미션 MSG_APPROACH_REASK).
+APPROACH_REASK = "안내를 받으시겠어요?"
 
 # 숫자로 끝나는 이름을 읽을 때 마지막 숫자의 받침(영·일·삼·육·칠·팔 있음, 이·사·오·구 없음).
 _DIGIT_HAS_BATCHIM = {
@@ -117,6 +119,7 @@ def baked_mission_ments() -> dict[str, str]:
         "mission_msg_wait_finish_ask": WAIT_FINISH_ASK,
         # 미션 요청 반응표(2026-10-08) — 대기 중 "취소"의 질문(결정 3).
         "mission_msg_wait_need_ask": WAIT_NEED_ASK,
+        "mission_msg_approach_reask": APPROACH_REASK,
     }
     out.update(wait_spot_sentences())
     out.update(wait_front_sentences())
```

</details>

- [ ] **Step 7: (사용자) 로봇 스택을 내리고 굽는다**

```bash
(cd vica-voice-llm && PYTHONPATH=~/CosyVoice:~/CosyVoice/third_party/Matcha-TTS    ~/venvs/cosyvoice/bin/python scripts/bake_one_cv.py --mission)
```

- [ ] **Step 8: 통과하는지 본다**

Run: `(cd vica-voice-llm && .venv/bin/python -m pytest tests/ -q -p no:cacheprovider)`
Expected: 전부 통과

- [ ] **Step 9: 두 저장소에 커밋한다** (push 하지 않는다)

```bash
git -C vica_ros2_ws add src/vica_mission_manager/test/test_reaction_rules.py src/vica_mission_manager/vica_mission_manager/mission_logic.py src/vica_mission_manager/vica_mission_manager/mission_manager_node.py
git -C vica_ros2_ws commit -m "feat(mission): 접근 질문에 못 알아들은 답이면 '안내를 받으시겠어요?'만 한 번 다시(다시 묻기, 사용자 승인)" -m "$VICA_TRAILER"
git -C vica-voice-llm add tests/test_mission_phrases.py src/mission_phrases.py
git -C vica-voice-llm add -f assets/baked/manifest.json assets/baked/mission_msg_approach_reask.wav
git -C vica-voice-llm commit -m "assets(voice): 접근 질문 다시 묻기 '안내를 받으시겠어요?'를 굽는다" -m "$VICA_TRAILER"
```


### Task 19: 실기 검증 (사용자 판정)

이 작업은 사용자가 정한 때에만 한다("완벽하게 계획을 세우기 전까진 시험 안 한다", 10-07). 판정은 로봇이 아니라 사람
기준이다 — 사용자가 헷갈리지 않았는가.

- [ ] **Step 1: 빌드·재시작** — 미션 `cd vica_ros2_ws && colcon build --packages-select vica_mission_manager` 뒤 미션 노드를
  다시 띄우고, 음성 노드도 다시 띄운다(굽기를 했으면 반드시). bag 을 걸면 `ros2 bag record`가 실제로 쓰는지
  확인한다.
- [ ] **Step 2: 시나리오** — 하나씩 밟고 "들은 말"과 "로봇이 한 일"을 적는다.

| # | 상황 | 사용자가 말함 | 통과 기준 |
| --- | --- | --- | --- |
| 1 | 안내 주행 중 | "기다려" → "다시 가자" | 멈추며 "잠시 멈추겠습니다…" → "OO로 다시 출발합니다" |
| 2 | 안내 주행 중 | "다 됐어" → "아니요" / "네" | "안내를 취소할까요?" → "안내를 계속하겠습니다." / 취소 |
| 3 | 안내 주행 중 | "다시 가자" | "지금 OO로 가는 중이에요." |
| 4 | 도착 질문 | "잠깐만" → "기다려 줘" | "네?" → 대기 안내 |
| 5 | 시간 질문 | "네" → "네" | 같은 질문 한 번 더 → "최대 30분…" 대기 |
| 6 | 시간 질문 | "대기하지 마" → "네" | "여기까지 안내를 마칠까요?" → "안내를 종료합니다" 홈 |
| 7 | 대기 중 | "취소" → "아니, 필요 없어" | "안내가 필요 없으신가요?" → 종료·홈 |
| 8 | 대기 중 | "취소" → "아니요" | → "안내를 계속하겠습니다." 계속 대기 |
| 9 | 대기 중 | "다 됐어" → 15초 침묵 → 침묵 | "어디로 모실까요?" → 한 번 더 → 계속 대기 |
| 10 | 홈 가는 중 | "비카야" → "기다려" | "네?" → M2′ → 직전 목적지 대기 장소로 간다 |
| 11 | 확인 질문 | "아니, 엘리베이터로 가자" → "응" | "네, 엘리베이터로 안내해드릴까요?" → 출발 |
| 12 | 접근 질문 | "응, 화장실 가고 싶어" → "응" | 수락·회전 → 손잡이 안내 → "화장실로 안내해드릴까요?" → 출발 |
| 13 | 안내 없음 | "학과사무실 어디야" → "응" | 정보 + 확인 질문(목적지 제안) → 출발. "알겠습니다"·"할게요" 없음 |
| 14 | 아무 질문 중 | 옆사람이 말함 | 로봇 목소리 하나 — 미션이 같은 질문 한 번, LLM 은 조용 |

- [ ] **Step 3: 기록** — 결과를 `devlog/2026-10-XX.md`(의미 있는 동작 결정·실기 결과, AGENTS.md 7절)에 남긴다. 인수인계
  문서의 LLM 칸(규칙 2·지시문)을 고칠 때는 먼저 사용자에게 묻는다.

## Self-Review

- **설계 대조.** 설계 2절(규칙 1·2·다시 묻기) → 작업 3~12·13~14. 3절(말별 공통 규칙) → 작업 3~7. 4절(바뀌는 칸 55개) → 반응표
  `PENDING` 56칸(설계의 "홈 가다 세운 뒤"는 시험에서 대기 장소 유무 두 갈래로 나눴다) + 질문 열 13칸은 작업 13. 5절(질문별 다시
  묻기 9행) → 확인 질문·취소 확인·도착·시간·대기 중 두 질문 = 작업 12, 다시 출발 확인 = 작업 16, 온보딩 = 바꾸지 않음, 접근
  질문 = 작업 18(승인 시). 6절(결정 5개) → 작업 9·10·8·10·13. 7절(문장) → 작업 6·8·10·17·18. 8절(음성) 1~6 → 작업 13·14·13·13·13·16.
  10절(하지 않는 것) — 앱·손잡이·긴급어·비상 멈춤 칸·온보딩 질문 중 요청은 손대지 않았다(`_react_idle`이 손잡이 잡기·온보딩
  중에는 None).
- **빈칸 검사.** "TBD"·"나중에"·"적절히" 없음. 모든 코드는 패치로 들어 있고 패치는 실제 코드 복사본에 적용해 확인했다.
- **이름 일관성.** `on_voice_intent`·`_react_by_table`·처리기 이름·`_ask`·`_confirm_prompt_for`·`_arm_confirm`·`QUESTION_REASK_SEC`·
  `MSG_*` 새 상수 넷 — 작업 사이에 같은 이름을 쓴다(패치를 순서대로 적용해 시험이 통과했다).
- **Review Focus.** 다섯 줄 모두 소유 작업의 시험으로 들어 있다.
- **남은 위험.** 시연(≈10-27) 3주 전에 대화 경로를 넓게 건드린다. 단계마다 시험이 통과하지만 실기는 작업 19 하나다 — 이상하면
  작업 단위로 되돌릴 수 있다(작업마다 커밋). 부정 질문 판정은 LLM 몫이라 단위 시험은 지시문 글자만 본다 — 실기 7·8번으로 확인한다.
