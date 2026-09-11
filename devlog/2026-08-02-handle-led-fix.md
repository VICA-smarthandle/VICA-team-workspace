# 스마트핸들 LED 좌우 종결 (2026-08-02)

2026-08-01 4.3절이 남긴 숙제 — **A/B 스트립의 물리적 좌우 실측** — 을 끝냈다.
노트북(x86_64)에서 펌웨어를 고쳐 실물에 올리고 bench로 확인했다. 상위 ROS의
임시 교환은 이미 걷어낸 상태이므로 이 문제는 이것으로 닫힌다.

작업 근거 문서는 `docs/handoff_laptop_firmware_and_apk.md`(같은 날 젯슨에서 작성)다.

## 1. 무엇이 틀려 있었나

`.ino` 주석의 핀-방향 표기가 반대였다.

```text
주석 표기   D9(좌측)  D8(우측)
실제        D8 = 왼쪽  D9 = 오른쪽
```

그 잘못된 표기를 따라 `STATE_LEFT`/`STATE_RIGHT` 두 `case`의 LED 설정이 서로
뒤바뀌어 있었다. 서보는 처음부터 옳았다.

## 2. 고친 것 — LED 두 줄만

`src/vica_user_guidance/firmware/smart_handle_firmware/smart_handle_firmware.ino`,
커밋 `0df48ad` (`tune/handle-guidance-2026-08-02`, push 완료).

두 `case`에서 `currentMode`와 `setA`/`setB` 두 줄만 서로 맞바꿨다.
`currentMode`는 주황 흐름선이 흐를 스트립을 정하고 `setA`/`setB`는 반대쪽을
하늘색 상시 점등으로 둔다. 둘은 항상 짝을 이뤄 반대여야 한다.

**`servoMoveTo` 줄은 건드리지 않았다.** 서보가 물리적으로 거꾸로 장착돼 있어
`STATE_LEFT`에서 `SERVO_RIGHT`를 부르는 것이 이미 올바른 보정이다. 상수명에
맞춰 "고치면" 반대로 움직인다.

상위 ROS에서 뒤집는 방식은 쓸 수 없다. 아두이노가 상태코드 하나로 LED와 서보를
같은 `case`에서 함께 정하므로 LED를 맞추면 서보가 함께 뒤집힌다. 2026-08-01에
실제로 그 실수를 했고, 지금은 `test_left_cue_sends_left_code`가 재발을 막는다.
그 시험이 빨간불이면 고칠 자리는 ROS가 아니라 `.ino`다.

## 3. 검증 — 이 문제의 종결 근거

ROS를 거치지 않고 펌웨어에 상태코드를 직접 넣어 확인했다. 상위 계층의 어떤
보정도 개입하지 않은 결과다.

```bash
arduino-cli compile --fqbn arduino:avr:nano firmware/smart_handle_firmware
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano firmware/smart_handle_firmware
python3 firmware/bench_test.py --port /dev/ttyUSB0 --hold 1
python3 firmware/bench_test.py --port /dev/ttyUSB0 --hold 2
```

| 보낸 코드 | 주황 흐름선 | 서보 | 판정 |
| --- | --- | --- | --- |
| `--hold 1` (STATE_LEFT) | 왼쪽 | 왼쪽 | PASS |
| `--hold 2` (STATE_RIGHT) | 오른쪽 | 오른쪽 | PASS |

빌드 크기 6102바이트(19%), 전역 325바이트(15%). 구형 부트로더 대응
(`cpu=atmega328old`)은 필요 없었다.

## 4. 노트북 작업 환경 메모

- `arduino-cli` 1.5.1은 `~/bin`에 있고 `PATH`에 등록돼 있지 않다. 매번
  `export PATH="$HOME/bin:$PATH"`가 필요하다. `arduino:avr` 1.8.8,
  Adafruit NeoPixel 1.15.5, Servo 1.3.0 설치 완료.
- 노트북에는 udev 규칙이 없어 `/dev/vica_smart_handle`이 아니라 `/dev/ttyUSB0`로
  잡힌다. FTDI FT232R serial `B003UMKG`로 대상 보드를 확인했다.
- `vica_ros2_ws`는 다른 세션이 `feat/home-return`을 잡고 있어 worktree
  (`/mnt/ssd/workspaces/tmp/handle-firmware`)로 접근했다.

## 5. 남은 일

1. **USB 케이블을 젯슨으로 되돌린다.** `ls -l /dev/vica_smart_handle`로 심볼릭
   링크가 다시 잡히는지 확인한다. 보드를 바꾼 것이 아니므로 udev 규칙은 그대로
   동작한다.
2. **실주행 확인.** 실제 회전에서 LED와 서보가 같은 쪽을 가리키는지 본다. 회전
   판정 임계값은 2026-08-02에 25도에서 20도로 낮췄다(`config/user_guidance.yaml`).
3. `tune/handle-guidance-2026-08-02`의 `dev` 머지는 실주행 확인 뒤에 한다.

## 6. APK — 별건으로 완료

핸드오프 문서 B절의 APK 빌드는 이 세션과 별개로 이미 끝나 있었다.
`chore/android-gradle-cleanup`(`d7a18be`, push 완료)에서 `--split-per-abi`로
3종을 빌드했고 실기 설치까지 마쳤다. release가 여전히 디버그 키로 서명된다는
점은 그대로다 — 다른 PC에서 만든 APK를 덮어쓰면 서명 불일치로 거부된다.
