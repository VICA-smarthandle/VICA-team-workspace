# 노트북(x86_64) 작업 핸드오프 — 펌웨어 LED 좌우 수정과 APK 빌드

작성 2026-08-02 (Jetson 세션). 대상은 **x86_64 리눅스 노트북**에서 이어받는 사람 또는
에이전트다. 두 작업 모두 Jetson(ARM64)에서는 할 수 없어 넘긴다.

| 작업 | 왜 Jetson에서 못 하나 |
| --- | --- |
| A. 스마트핸들 펌웨어 LED 좌우 수정 | `arduino-cli`도 Arduino IDE도 설치돼 있지 않다 |
| B. 관리자 앱 APK 빌드 | Flutter가 `linux-arm64` 호스트용 Android `gen_snapshot`을 배포하지 않는다 |

두 작업은 서로 독립이다. 하나만 해도 된다.

## ✅ 두 작업 모두 끝났다 (2026-08-02, 노트북)

이 문서를 새로 여는 사람은 **아래 절차를 다시 밟을 필요가 없다.** 남은 것은 C절뿐이다.

| 작업 | 결과 |
| --- | --- |
| A. 펌웨어 | 수정·업로드·bench 검증 완료. `vica_ros2_ws` `tune/handle-guidance-2026-08-02` `0df48ad` (push 완료) |
| B. APK | `--split-per-abi` 3종 빌드·실기 설치 완료. `VICA_Supervisor` `chore/android-gradle-cleanup` `d7a18be` (push 완료) |

A-7 검증 결과는 코드 1·2 모두 PASS(주황 흐름선과 서보가 같은 쪽)였다. 상세 기록은
`devlog/2026-08-02-handle-led-fix.md`에 있다. 아래 A·B절은 재현·되돌리기용으로 남긴다.

---

## 0. 시작 전 확인

```bash
uname -m          # x86_64 여야 한다. aarch64면 이 문서의 대상 기기가 아니다
```

저장소는 4개로 나뉜다. 이 문서가 쓰는 것은 둘이다.

| 작업 | 저장소 | 브랜치 |
| --- | --- | --- |
| A. 펌웨어 | `vica_ros2_ws` (`VICA-smarthandle/vica_ros2_ws`) | `tune/handle-guidance-2026-08-02` |
| B. APK | `VICA_Supervisor` (`myw411/VICA_Supervisor`) | `chore/android-gradle-cleanup` |

**공통 규칙** (`AGENTS.md`·`GOVERNANCE.md`):

- commit과 push는 **사용자가 요청할 때만** 한다.
- 머지는 `dev`로만 한다. `main`은 건드리지 않는다.
- 커밋 메시지는 한국어 평서형, `<type>(<scope>): <요약>` 형식.

---

## A. 스마트핸들 펌웨어 — LED 좌우만 고친다

### A-1. 확정된 사실 (2026-08-02 실측)

ROS를 거치지 않고 펌웨어에 1바이트 상태코드를 직접 넣어 확인했다. 상위 계층의
어떤 보정도 개입하지 않은 결과다.

```text
코드 1 (STATE_LEFT)   서보 왼쪽   정상    주황 LED 오른쪽   반대
코드 2 (STATE_RIGHT)  서보 오른쪽  정상    주황 LED 왼쪽    반대
```

- **D8(스트립 A)이 왼쪽, D9(스트립 B)가 오른쪽이다.** `.ino` 주석의 `D9(좌측)`,
  `D8(우측)` 표기가 반대로 적혀 있었다.
- **서보는 이미 올바르다.** 서보가 물리적으로 거꾸로 장착돼 있고, 펌웨어가
  `case STATE_LEFT`에서 `SERVO_RIGHT`를 부르는 방식으로 이미 상쇄하고 있다.

### A-2. 🚫 하지 말 것

1. **`servoMoveTo(...)` 줄을 건드리지 말 것.** 상수명이 반대로 보이는 것은 정상이며,
   "이름에 맞게 고치면" 서보가 반대로 움직인다.
2. **ROS 쪽(`guidance_priority.py`)에서 좌우를 뒤집지 말 것.** 2026-08-01에 그렇게
   했다가 LED는 맞았지만 **서보가 함께 뒤집혔다** — 아두이노는 상태코드 하나로 LED와
   서보를 같은 `case`에서 함께 정하기 때문이다. 지금은 그 교환을 걷어냈고
   `test_left_cue_sends_left_code`가 재발을 막는다. 그 시험이 빨간불이면 고칠 자리는
   ROS가 아니라 `.ino`다.
3. 이 수정으로 `protocol.py`의 상태코드 값은 **바뀌지 않는다.** 건드리면
   `test_protocol.py`가 깨진다.

### A-3. 고칠 내용 — 두 `case`의 LED 두 줄만 맞바꾼다

파일: `src/vica_user_guidance/firmware/smart_handle_firmware/smart_handle_firmware.ino`

**지금 (틀림)**

```cpp
    case STATE_LEFT:
      currentMode = WAVE_B;   // D9 = 실제로는 우측 [반대. 위 주석 참고]
      setA(SKY); setB(OFF);
      servoMoveTo(SERVO_RIGHT);   // 실측: 서보가 왼쪽으로 이동 (정상)
      break;

    case STATE_RIGHT:
      currentMode = WAVE_A;   // D8 = 실제로는 좌측 [반대. 위 주석 참고]
      setA(OFF); setB(SKY);
      servoMoveTo(SERVO_LEFT);    // 실측: 서보가 오른쪽으로 이동 (정상)
      break;
```

**고친 뒤**

```cpp
    case STATE_LEFT:
      currentMode = WAVE_A;   // D8 = 왼쪽 (2026-08-02 실측)
      setB(SKY); setA(OFF);   // 주황이 흐르는 A는 끄고 반대쪽 B를 하늘색으로
      servoMoveTo(SERVO_RIGHT);   // ← 그대로. 건드리지 않는다
      break;

    case STATE_RIGHT:
      currentMode = WAVE_B;   // D9 = 오른쪽 (2026-08-02 실측)
      setA(SKY); setB(OFF);
      servoMoveTo(SERVO_LEFT);    // ← 그대로. 건드리지 않는다
      break;
```

`currentMode`가 정하는 것은 **주황 흐름선이 흐를 스트립**이고, `setA/setB`는 반대쪽을
하늘색 상시 점등으로 둔다. 둘은 항상 짝을 이뤄 반대여야 한다.

수정 후 그 위 주석 블록의 `[아직 안 고침]` 표시와 "이 저장소에서는 아직 고치지
않았다" 문단을 **함께 갱신한다.** 남겨두면 다음 사람이 또 헷갈린다.

### A-4. 하드웨어 연결

스마트핸들 아두이노(Arduino Nano, FTDI FT232R, serial `B003UMKG`)는 지금 **Jetson에
USB로 연결돼 있다.** 노트북에서 올리려면 그 USB 케이블을 노트북으로 옮겨야 한다.

- 옮기기 전에 Jetson에서 `user_guidance_driver_node`가 떠 있지 않은지 확인한다.
- 노트북에는 udev 규칙이 없으므로 `/dev/vica_smart_handle`이 아니라
  **`/dev/ttyUSB0`** 같은 이름으로 잡힌다. 아래 명령의 포트를 실제 이름으로 바꾼다.
- 노트북 사용자가 `dialout` 그룹에 없으면 포트 열기가 거부된다:
  `sudo usermod -aG dialout $USER` 후 재로그인.

### A-5. 환경 준비

```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
  | BINDIR=~/bin sh
export PATH="$HOME/bin:$PATH"

arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli lib install "Adafruit NeoPixel"     # Servo는 AVR 코어에 함께 온다
```

### A-6. 빌드와 업로드

`src/vica_user_guidance/`에서 실행한다.

```bash
arduino-cli compile --fqbn arduino:avr:nano firmware/smart_handle_firmware
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano \
    firmware/smart_handle_firmware
```

업로드가 `stk500_recv(): programmer is not responding`으로 실패하면 구형 부트로더다.
FTDI FT232R을 쓰는 Nano는 이 경우가 흔하다.

```bash
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano:cpu=atmega328old \
    firmware/smart_handle_firmware
```

### A-7. 검증 — 이걸 하지 않으면 끝난 게 아니다

ROS 없이 단독으로 확인한다. 로봇과 분리된 상태여도 된다.

```bash
python3 firmware/bench_test.py --port /dev/ttyUSB0 --hold 1   # Ctrl+C로 중단
python3 firmware/bench_test.py --port /dev/ttyUSB0 --hold 2
```

**합격 기준**

| 보낸 코드 | 주황 흐름선 | 서보 |
| --- | --- | --- |
| `--hold 1` (STATE_LEFT) | **왼쪽** | **왼쪽** |
| `--hold 2` (STATE_RIGHT) | **오른쪽** | **오른쪽** |

서보가 반대로 나오면 A-2의 1번을 어긴 것이다. `servoMoveTo` 줄을 원래대로 되돌린다.

전체 항목을 보려면 `python3 firmware/bench_test.py --port /dev/ttyUSB0 --all`.

### A-8. 되돌리기

업로드한 펌웨어가 이상하면 이전 커밋의 `.ino`를 다시 올리면 된다. **소스를 되돌리는
것만으로는 실물이 바뀌지 않는다** — 반드시 다시 업로드해야 한다.

```bash
git stash                      # 또는 git checkout -- <ino 경로>
arduino-cli compile --fqbn arduino:avr:nano firmware/smart_handle_firmware
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano firmware/smart_handle_firmware
```

### A-9. 참고 — Jetson에서 시도해 볼 수도 있다

`arduino-cli`는 Linux ARM64 바이너리를 배포하고 `arduino:avr` 코어도 aarch64 툴체인을
포함한다. 즉 **Jetson에서도 될 가능성이 있다.** 아직 시도하지 않았다(설치는 사용자
승인이 필요하다). 노트북 작업이 번거로우면 Jetson에서 A-5~A-7을 그대로 해 보는 것도
방법이다. 그 경우 포트는 `/dev/vica_smart_handle`이다.

---

## B. 관리자 앱 APK 빌드

### B-1. 배경

`android/`에 Groovy DSL과 Kotlin DSL 두 세트가 함께 있어 APK 빌드가 구성 단계에서
막혀 있었다. Gradle이 Groovy 파일을 먼저 고르는데 그쪽 AGP가 8.6.0이라 wrapper의
Gradle 9.1.0과 맞지 않는다. 2026-08-02에 Groovy 세트를 지웠고, Jetson에서
`./gradlew :app:tasks`가 **BUILD SUCCESSFUL**로 통과하는 것까지 확인했다.
남은 것은 Dart AOT 컴파일뿐이고 그게 x86_64를 요구한다.

### B-2. 환경

Jetson과 같은 버전을 쓴다.

```bash
git clone -b stable https://github.com/flutter/flutter.git ~/development/flutter
cd ~/development/flutter && git checkout 3.44.2
export PATH="$PATH:$HOME/development/flutter/bin"

sudo apt install openjdk-17-jdk            # Gradle 9가 JDK 17을 요구한다
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0" \
           "ndk;28.2.13676358"
sdkmanager --licenses
flutter doctor                              # Android toolchain ✓ 확인
```

`compileSdk 36 / minSdk 24 / targetSdk 36`이다. minSdk 24는 안드로이드 7.0 이상이면
설치된다는 뜻이다.

### B-3. 빌드

```bash
git clone https://github.com/myw411/VICA_Supervisor.git
cd VICA_Supervisor
git checkout chore/android-gradle-cleanup
flutter pub get
flutter build apk --release --split-per-abi
```

산출물은 `build/app/outputs/flutter-apk/`에 나온다. 실기 대부분은
**`app-arm64-v8a-release.apk`**다.

`android/local.properties`는 gitignore 대상이라 노트북에서 자동 생성된다 — Jetson
경로가 따라오지 않는다.

### B-4. 설치와 첫 설정

```bash
adb install -r build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

설치 후 **앱 설정 화면에서 접속 주소를 반드시 바꾼다.** 기본값이 `127.0.0.1`이라
폰에서는 아무것도 표시되지 않는다.

```text
ws://<젯슨IP>:9090        rosbridge
http://<젯슨IP>:8000      지도 이미지
```

Jetson IP는 DHCP라 공유기를 재부팅하면 바뀐다. `hostname -I`로 확인한다.

### B-5. 서명 주의

`android/app/build.gradle.kts`에 `// TODO: Add your own signing config`가 그대로 있어
**release가 디버그 키로 서명**된다. 설치는 되지만 디버그 키는 PC마다 다르므로, 다른
PC에서 만든 APK를 같은 폰에 덮어씌우면 서명 불일치로 거부된다(지웠다 다시 깔아야
한다). 계속 배포할 계획이면 공용 키스토어를 만들어야 한다 — 이 문서 범위 밖이다.

---

## C. 끝난 뒤 Jetson에서 할 일

1. **펌웨어**: USB 케이블을 Jetson으로 되돌리고 `/dev/vica_smart_handle` 심볼릭 링크가
   다시 잡히는지 확인한다(`ls -l /dev/vica_smart_handle`). 보드를 교체한 게 아니라면
   udev 규칙은 그대로 동작한다.
2. **실주행 확인**: 실제 회전에서 LED와 서보가 같은 쪽을 가리키는지 본다. 회전 판정
   임계값은 2026-08-02에 25도에서 **20도**로 낮췄다(`config/user_guidance.yaml`).
3. **기록**: 결과를 `devlog/`에 남긴다. 특히 A-7 검증 결과는 이 문제의 종결 근거다.

## D. 관련 문서

- `devlog/2026-08-01-drive-tuning-and-duplicate-stack.md` 4.3절 — 문제가 처음 드러난 경위
- `devlog/2026-07-28-smart-handle-guidance-plan.md` — 스마트핸들 설계 계획서
- `vica_ros2_ws/src/vica_user_guidance/README.md` — 펌웨어·udev·bench 도구 사용법
