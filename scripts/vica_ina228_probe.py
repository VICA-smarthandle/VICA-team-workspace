#!/usr/bin/env python3
"""INA228 적산계(전력·전하 누적 측정기)를 젯슨 I2C 에서 직접 읽는 진단·기록 도구.

왜 이 도구인가 — 젯슨 커널의 ina2xx.ko 는 INA219/226/230/231 까지만 알고 INA228 은
모른다(`modinfo ina2xx` 의 alias 목록). 그래서 /sys/class/hwmon 에 저절로 나타나지
않고, 사용자 공간에서 smbus2 로 레지스터를 직접 읽어야 한다. 이 스크립트가 그 일을
한다. ROS 노드가 아니라 진단 도구다 — 토픽을 만들지 않는다. [TEST ONLY]
운영 경로(Mission·Safety·CAN)와 무관하다.

배선 사실 (2026-09-03 젯슨 실측 + Seeed 문서):
  - 캐리어보드는 Seeed reComputer Robotics J401 이다(/proc/device-tree/model).
    40핀 헤더가 없고 GH1.25 4핀 I2C 커넥터 두 개가 있다:
        IIC0 (J7) → /dev/i2c-1 (c240000.i2c)  ← 보드 자체 INA3221 이 0x40 을 이미 쓴다
        IIC1 (J6) → /dev/i2c-7 (c250000.i2c)  ← 0x21 GPIO 확장기뿐. INA228 은 여기 권장
    근거: Seeed 위키 "Robotics J401 Getting Started" I2C 절, 사용자 매뉴얼 표 27·28.
    두 커넥터 모두 핀 순서는 1 GND · 2 SDA · 3 SCL · 4 VDD_I2C1(전원) 이다(매뉴얼 표 27·28).
    모듈 쪽 순서가 다르면(예: Adafruit STEMMA QT 는 GND·V+·SDA·SCL) 케이블에서 바꿔 꽂는다.
    VDD_I2C1 의 실제 전압은 매뉴얼 본문에 숫자가 없다 [미검증] — 급전 전 멀티미터로 잰다.
  - 커넥터 신호 레벨은 3.3 V (I2C1_SDA_3V3_LS). INA228 은 VS 2.7~5.5 V, SDA/SCL 은
    VIH 1.2 V 이상이면 되므로 3.3 V 급전이 맞다. 모듈 풀업이 5 V 에 매달리면 안 된다.
  - /dev/i2c-5 (31b0000) 는 이 보드에서 미배선이라 스캔하면 dmesg 에
    "tegra-i2c 31b0000.i2c: I2C transfer timed out" 이 찍힌다. 고장이 아니다.
    기본 스캔 대상에서 뺐다.

INA228 요점 (TI 데이터시트 SLYS021A, 2022-05):
  - 주소 0x40~0x4F, A1/A0 핀 조합(표 7-2). 기본(둘 다 GND) 0x40.
  - 신분증: 0x3E MANUFACTURER_ID = 0x5449("TI"), 0x3F DEVICE_ID = 0x228x.
  - VSHUNT/VBUS/CURRENT 는 24비트 중 상위 20비트(하위 4비트 예약, >>4), 2의 보수.
    POWER 24비트 부호 없음, ENERGY 40비트 부호 없음, CHARGE 40비트 2의 보수.
  - LSB: VSHUNT 312.5 nV(ADCRANGE 0) / 78.125 nV(1), VBUS 195.3125 µV,
    DIETEMP 7.8125 m°C.
  - CURRENT_LSB = 최대 예상 전류 / 2^19,
    SHUNT_CAL = 13107.2e6 × CURRENT_LSB × R_SHUNT (ADCRANGE=1 이면 ×4).
    SHUNT_CAL 이 0 이면 CURRENT·POWER·ENERGY·CHARGE 가 전부 0 이다(8.1.2).
  - Power[W] = 3.2 × CURRENT_LSB × POWER
    Energy[J] = 16 × 3.2 × CURRENT_LSB × ENERGY
    Charge[C] = CURRENT_LSB × CHARGE
  - 적산 레지스터는 휘발성이다. 전원이 끊기면 0 이 되고, 40비트를 넘치면 0 부터
    다시 센다(DIAG_ALRT ENERGYOF/CHARGEOF). CONFIG RSTACC(bit14) 로 언제든 0 으로.

새 I2C 장치를 꽂았을 때 확인 순서:
  1. 어느 커넥터가 어느 버스인지 (위 표)
  2. 주소 충돌: `i2cdetect -y -r <bus>` 의 UU 는 커널이 점유한 주소다. 같은 주소에 새
     장치를 두면 둘이 동시에 답해 값이 깨진다 → 다른 커넥터 또는 A0/A1 로 주소 변경
  3. 전압·풀업: 3.3 V 급전, 풀업은 3.3 V 쪽에만
  4. 신분증: `check` 가 0x5449 / 0x228x 를 보여야 한다
  5. 션트 저항값(모듈 실크 또는 판매 페이지)을 --shunt 로 넘겨야 전류·적산이 의미를 갖는다
  6. 부호: 전류가 음수면 IN+/IN– 가 뒤집힌 것. 공통 GND 필수. VBUS 는 85 V 상한.

사용법:
    python3 scripts/vica_ina228_probe.py scan                    # i2c-7·1 에서 INA228 찾기 (읽기 전용)
    python3 scripts/vica_ina228_probe.py check --bus 7           # 신분증·설정·진단 비트 (읽기 전용)
    python3 scripts/vica_ina228_probe.py read --bus 7 --shunt 0.015 --max-current 10
    python3 scripts/vica_ina228_probe.py read --bus 7 --shunt 0.015 --max-current 10 \
        --csv ~/vica_power_logs/run1.csv
    python3 scripts/vica_ina228_probe.py reset-acc --bus 7      # ENERGY·CHARGE 를 0 으로
    python3 scripts/vica_ina228_probe.py selftest                # 하드웨어 없이 변환 수식 검증
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

try:
    from smbus2 import SMBus
except ImportError:  # selftest 는 smbus2 없이도 돈다
    SMBus = None

# ---- 레지스터 주소 (데이터시트 표 7-3) ----
REG_CONFIG = 0x00
REG_ADC_CONFIG = 0x01
REG_SHUNT_CAL = 0x02
REG_VSHUNT = 0x04
REG_VBUS = 0x05
REG_DIETEMP = 0x06
REG_CURRENT = 0x07
REG_POWER = 0x08
REG_ENERGY = 0x09
REG_CHARGE = 0x0A
REG_DIAG_ALRT = 0x0B
REG_MANUFACTURER_ID = 0x3E
REG_DEVICE_ID = 0x3F

MANUFACTURER_TI = 0x5449
DEVICE_INA228 = 0x228        # DEVICE_ID 상위 12비트 (하위 4비트는 리비전)
DEVICE_ID_INA3221 = 0x3220   # 보드 자체 모니터. 0x3E/0x3F 로 읽어도 같은 값을 준다(실측)

VSHUNT_LSB = (312.5e-9, 78.125e-9)   # [ADCRANGE 0, ADCRANGE 1]
VSHUNT_FULL_SCALE = (0.16384, 0.04096)
VBUS_LSB = 195.3125e-6
DIETEMP_LSB = 7.8125e-3
ADC_CONFIG_DEFAULT = 0xFB68          # 연속 측정(버스·션트·온도), 1052 µs, 평균 1
CONFIG_RST = 1 << 15
CONFIG_RSTACC = 1 << 14
CONFIG_ADCRANGE = 1 << 4

DIAG_BITS = {
    11: "ENERGYOF", 10: "CHARGEOF", 9: "MATHOF", 7: "TMPOL",
    6: "SHNTOL", 5: "SHNTUL", 4: "BUSOL", 3: "BUSUL", 2: "POL",
}
DEFAULT_BUSES = (7, 1)
ADDR_RANGE = range(0x40, 0x50)


# ---- 순수 변환 함수 (하드웨어 없이 검증 가능) ----
def to_signed(value, bits):
    """bits 비트 2의 보수 정수를 파이썬 int 로."""
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def decode_20bit(raw24):
    """24비트 레지스터의 상위 20비트를 부호 있는 값으로 (VSHUNT/VBUS/CURRENT)."""
    return to_signed((raw24 >> 4) & 0xFFFFF, 20)


def decode_charge(raw40):
    return to_signed(raw40 & 0xFFFFFFFFFF, 40)


def calc_calibration(shunt_ohm, max_current_a, adcrange):
    """(CURRENT_LSB, SHUNT_CAL) — 데이터시트 식 (2)·(3)."""
    if shunt_ohm <= 0 or max_current_a <= 0:
        raise ValueError("션트 저항과 최대 전류는 양수여야 한다")
    if max_current_a * shunt_ohm > VSHUNT_FULL_SCALE[adcrange]:
        raise ValueError(
            f"최대 전류 {max_current_a} A × 션트 {shunt_ohm} Ω = "
            f"{max_current_a * shunt_ohm * 1e3:.1f} mV 가 ADCRANGE {adcrange} 의 "
            f"풀스케일 {VSHUNT_FULL_SCALE[adcrange] * 1e3:.2f} mV 를 넘는다")
    current_lsb = max_current_a / (1 << 19)
    cal = 13107.2e6 * current_lsb * shunt_ohm * (4 if adcrange else 1)
    cal_int = int(round(cal))
    if not 0 < cal_int <= 0xFFFF:
        raise ValueError(f"SHUNT_CAL {cal_int} 가 16비트 범위를 벗어난다")
    return current_lsb, cal_int


def diag_flags(diag):
    return [name for bit, name in DIAG_BITS.items() if diag & (1 << bit)]


# ---- 장치 접근 ----
class Ina228:
    def __init__(self, bus_no, addr, force=False):
        if SMBus is None:
            raise SystemExit("smbus2 가 없다: pip3 install smbus2 (젯슨엔 0.6.0 설치돼 있음)")
        self.bus = SMBus(bus_no, force=force)
        self.addr = addr
        self.current_lsb = None

    def close(self):
        self.bus.close()

    def _read(self, reg, n):
        data = self.bus.read_i2c_block_data(self.addr, reg, n)
        value = 0
        for b in data:
            value = (value << 8) | b
        return value

    def read16(self, reg):
        return self._read(reg, 2)

    def read24(self, reg):
        return self._read(reg, 3)

    def read40(self, reg):
        return self._read(reg, 5)

    def write16(self, reg, value):
        self.bus.write_i2c_block_data(self.addr, reg, [(value >> 8) & 0xFF, value & 0xFF])

    def identify(self):
        return self.read16(REG_MANUFACTURER_ID), self.read16(REG_DEVICE_ID)

    def is_ina228(self):
        mfg, dev = self.identify()
        return mfg == MANUFACTURER_TI and (dev >> 4) == DEVICE_INA228

    def configure(self, shunt_ohm, max_current_a, adcrange=0, reset_acc=False):
        self.current_lsb, cal = calc_calibration(shunt_ohm, max_current_a, adcrange)
        config = (CONFIG_ADCRANGE if adcrange else 0) | (CONFIG_RSTACC if reset_acc else 0)
        self.write16(REG_CONFIG, config)
        self.write16(REG_ADC_CONFIG, ADC_CONFIG_DEFAULT)
        self.write16(REG_SHUNT_CAL, cal)
        self.adcrange = adcrange
        return cal

    def reset_accumulators(self):
        config = self.read16(REG_CONFIG)
        self.write16(REG_CONFIG, config | CONFIG_RSTACC)

    def sample(self):
        adcrange = (self.read16(REG_CONFIG) >> 4) & 1
        vshunt = decode_20bit(self.read24(REG_VSHUNT)) * VSHUNT_LSB[adcrange]
        vbus = decode_20bit(self.read24(REG_VBUS)) * VBUS_LSB
        temp = to_signed(self.read16(REG_DIETEMP), 16) * DIETEMP_LSB
        s = {"vbus_v": vbus, "vshunt_v": vshunt, "temp_c": temp,
             "diag": self.read16(REG_DIAG_ALRT)}
        if self.current_lsb:
            lsb = self.current_lsb
            s["current_a"] = decode_20bit(self.read24(REG_CURRENT)) * lsb
            s["power_w"] = self.read24(REG_POWER) * 3.2 * lsb
            s["energy_j"] = self.read40(REG_ENERGY) * 16 * 3.2 * lsb
            s["charge_c"] = decode_charge(self.read40(REG_CHARGE)) * lsb
        return s


# ---- 서브커맨드 ----
def cmd_scan(args):
    """0x40~0x4F 를 훑어 신분증으로 INA228 을 가려낸다. 읽기 전용."""
    found = []
    for bus_no in args.buses:
        print(f"--- /dev/i2c-{bus_no} ---")
        for addr in ADDR_RANGE:
            try:
                dev = Ina228(bus_no, addr, force=True)
                mfg, did = dev.identify()
                dev.close()
            except OSError:
                continue
            if mfg == MANUFACTURER_TI and (did >> 4) == DEVICE_INA228:
                tag = f"INA228 (rev {did & 0xF})  ← 찾았다"
                found.append((bus_no, addr))
            elif did == DEVICE_ID_INA3221:
                tag = "INA3221 — 보드 자체 전력 모니터(커널 점유). INA228 아님"
            else:
                tag = f"다른 장치 또는 무응답 데이터 (mfg=0x{mfg:04X} dev=0x{did:04X})"
            print(f"  0x{addr:02X}: {tag}")
    if found:
        for bus_no, addr in found:
            print(f"\n결과: INA228 발견 — /dev/i2c-{bus_no} 주소 0x{addr:02X}. "
                  f"다음: check --bus {bus_no} --addr 0x{addr:02X}")
        return 0
    print("\n결과: INA228 을 찾지 못했다. 스크립트 머리말의 '확인 순서' 1~3 을 본다.")
    return 1


def cmd_check(args):
    """신분증·설정·진단 비트·보정 없이 읽을 수 있는 값. 읽기 전용."""
    dev = Ina228(args.bus, args.addr)
    try:
        mfg, did = dev.identify()
        ok = mfg == MANUFACTURER_TI and (did >> 4) == DEVICE_INA228
        print(f"MANUFACTURER_ID 0x{mfg:04X} (기대 0x5449)  DEVICE_ID 0x{did:04X} (기대 0x228x)"
              f"  → {'INA228 맞음' if ok else 'INA228 아님'}")
        if not ok:
            return 1
        config = dev.read16(REG_CONFIG)
        adc = dev.read16(REG_ADC_CONFIG)
        cal = dev.read16(REG_SHUNT_CAL)
        diag = dev.read16(REG_DIAG_ALRT)
        print(f"CONFIG 0x{config:04X}  ADCRANGE={'±40.96mV' if config & CONFIG_ADCRANGE else '±163.84mV'}")
        print(f"ADC_CONFIG 0x{adc:04X}  MODE=0x{adc >> 12:X} "
              f"({'연속 측정' if adc >> 12 >= 9 else '단발/셧다운'})  (리셋 기본 0xFB68)")
        print(f"SHUNT_CAL {cal}  → {'보정 안 됨: 전류·전력·적산이 전부 0 으로 나온다' if cal == 0 else '보정값 있음'}")
        flags = diag_flags(diag)
        print(f"DIAG_ALRT 0x{diag:04X}  MEMSTAT={'정상' if diag & 1 else '트림 메모리 체크섬 오류'}"
              f"  플래그={flags or '없음'}")
        s = dev.sample()
        print(f"VBUS {s['vbus_v']:.4f} V   VSHUNT {s['vshunt_v'] * 1e3:.4f} mV   "
              f"온도 {s['temp_c']:.2f} °C   (션트값 없이도 읽히는 값)")
        return 0
    finally:
        dev.close()


def cmd_reset_acc(args):
    dev = Ina228(args.bus, args.addr)
    try:
        if not dev.is_ina228():
            print("INA228 이 아니다. 중단.")
            return 1
        dev.reset_accumulators()
        time.sleep(0.05)
        print(f"ENERGY raw={dev.read40(REG_ENERGY)}  CHARGE raw={dev.read40(REG_CHARGE)}  (0 이면 성공)")
        return 0
    finally:
        dev.close()


def cmd_read(args):
    dev = Ina228(args.bus, args.addr)
    writer = None
    fh = None
    try:
        if not dev.is_ina228():
            print("INA228 이 아니다. 중단.")
            return 1
        cal = dev.configure(args.shunt, args.max_current, args.adcrange, reset_acc=args.reset_acc)
        print(f"보정: 션트 {args.shunt} Ω, 최대 {args.max_current} A → "
              f"CURRENT_LSB {dev.current_lsb * 1e6:.3f} µA, SHUNT_CAL {cal}, ADCRANGE {args.adcrange}")
        if args.csv:
            os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
            fh = open(args.csv, "w", newline="")
            writer = csv.writer(fh)
            writer.writerow(["time", "vbus_v", "vshunt_mv", "current_a", "power_w",
                             "energy_j", "energy_wh", "energy_sw_j", "charge_c", "charge_ah",
                             "temp_c", "flags"])
        print(f"{'시각':8s} {'V':>8s} {'A':>8s} {'W':>8s} {'E_reg Wh':>10s} {'E_sw Wh':>9s} "
              f"{'Q Ah':>8s} {'°C':>6s}  플래그")
        time.sleep(0.01)
        energy_sw = 0.0
        last = time.monotonic()
        while True:
            s = dev.sample()
            now = time.monotonic()
            energy_sw += s["power_w"] * (now - last)   # 소프트웨어 적분 — 칩 적산과 대조용
            last = now
            flags = diag_flags(s["diag"])
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"{stamp:8s} {s['vbus_v']:8.3f} {s['current_a']:8.3f} {s['power_w']:8.3f} "
                  f"{s['energy_j'] / 3600:10.4f} {energy_sw / 3600:9.4f} "
                  f"{s['charge_c'] / 3600:8.4f} {s['temp_c']:6.1f}  {' '.join(flags)}")
            if writer:
                writer.writerow([datetime.now().isoformat(timespec="milliseconds"),
                                 f"{s['vbus_v']:.5f}", f"{s['vshunt_v'] * 1e3:.5f}",
                                 f"{s['current_a']:.5f}", f"{s['power_w']:.5f}",
                                 f"{s['energy_j']:.4f}", f"{s['energy_j'] / 3600:.6f}",
                                 f"{energy_sw:.4f}", f"{s['charge_c']:.4f}",
                                 f"{s['charge_c'] / 3600:.6f}", f"{s['temp_c']:.2f}",
                                 " ".join(flags)])
                fh.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n종료")
        return 0
    finally:
        if fh:
            fh.close()
        dev.close()


def cmd_selftest(_args):
    """데이터시트 예제 값으로 변환 수식을 검증한다 (8.2.2 · 표 8-4)."""
    LSB_EX = 10.0 / (1 << 19)   # 표 8-4 의 CURRENT_LSB
    checks = [
        ("VSHUNT 311040d → 0.0972 V", decode_20bit(311040 << 4) * VSHUNT_LSB[0], 0.0972, 1e-6),
        ("VBUS 245760d → 48 V", decode_20bit(245760 << 4) * VBUS_LSB, 48.0, 1e-9),
        ("DIETEMP 3200d → 25 °C", to_signed(3200, 16) * DIETEMP_LSB, 25.0, 1e-9),
        ("20비트 음수 0xFFFFF0 → -1", decode_20bit(0xFFFFF0), -1, 0),
        ("40비트 CHARGE 최상위 비트 → 음수", decode_charge(1 << 39), -(1 << 39), 0),
        ("Adafruit 기본 0.015 Ω/10 A → SHUNT_CAL 3750", calc_calibration(0.015, 10.0, 0)[1], 3750, 0),
        ("ADCRANGE 1 은 ×4", calc_calibration(0.015, 2.0, 1)[1], 3000, 0),
        ("표 8-4: 16.2 mΩ/10 A → SHUNT_CAL 4050 (FD2h)", calc_calibration(0.0162, 10.0, 0)[1], 4050, 0),
        ("표 8-4: CURRENT_LSB 19.073486 µA", calc_calibration(0.0162, 10.0, 0)[0], 19.073486e-6, 1e-12),
        ("표 8-4: CURRENT 314572d → 6 A (표는 반올림)", decode_20bit(314572 << 4) * LSB_EX, 6.0, 1e-4),
        ("표 8-4: POWER 4718604d → 288 W", 4718604 * 3.2 * LSB_EX, 288.0, 1e-3),
        ("표 8-4: ENERGY 1061683200d → 1036800 J", 1061683200 * 16 * 3.2 * LSB_EX, 1036800.0, 1.0),
        ("표 8-4: CHARGE 1132462080d → 21600 C", decode_charge(1132462080) * LSB_EX, 21600.0, 1e-3),
        ("표 8-4 본문: VSHUNT 0xB4100 → -0.0972 V", decode_20bit(0xB4100 << 4) * VSHUNT_LSB[0], -0.0972, 1e-6),
    ]
    bad = 0
    for name, got, want, tol in checks:
        ok = abs(got - want) <= tol
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {name}: got {got}")
    try:
        calc_calibration(0.1, 10.0, 0)
        print("BAD 풀스케일 초과를 못 잡았다")
        bad += 1
    except ValueError as e:
        print(f"OK  풀스케일 초과 거부: {e}")
    print("selftest", "통과" if bad == 0 else f"실패 {bad}건")
    return 1 if bad else 0


def parse_int(text):
    return int(text, 0)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="버스를 훑어 INA228 을 찾는다 (읽기 전용)")
    s.add_argument("--buses", type=int, nargs="+", default=list(DEFAULT_BUSES),
                   help="훑을 /dev/i2c-N 번호 (기본 7 1; 5 는 미배선이라 타임아웃만 남긴다)")
    s.set_defaults(func=cmd_scan)

    for name, func, help_ in (("check", cmd_check, "신분증·설정·진단 비트 (읽기 전용)"),
                              ("reset-acc", cmd_reset_acc, "ENERGY·CHARGE 적산을 0 으로"),
                              ("read", cmd_read, "보정 후 주기적으로 읽는다")):
        q = sub.add_parser(name, help=help_)
        q.add_argument("--bus", type=int, default=7, help="/dev/i2c-N (IIC1=7, IIC0=1)")
        q.add_argument("--addr", type=parse_int, default=0x40, help="I2C 주소 (기본 0x40)")
        q.set_defaults(func=func)
        if name == "read":
            q.add_argument("--shunt", type=float, required=True, help="션트 저항 [Ω] (예: 0.015)")
            q.add_argument("--max-current", type=float, required=True, help="최대 예상 전류 [A]")
            q.add_argument("--adcrange", type=int, choices=(0, 1), default=0,
                           help="0=±163.84 mV(기본), 1=±40.96 mV(작은 션트·정밀)")
            q.add_argument("--interval", type=float, default=1.0, help="출력 주기 [s]")
            q.add_argument("--csv", help="CSV 기록 경로")
            q.add_argument("--reset-acc", action="store_true", help="시작할 때 적산을 0 으로")

    t = sub.add_parser("selftest", help="하드웨어 없이 변환 수식 검증")
    t.set_defaults(func=cmd_selftest)

    args = p.parse_args()
    try:
        sys.exit(args.func(args))
    except OSError as e:
        bus = getattr(args, "bus", "?")
        addr = getattr(args, "addr", None)
        where = f"/dev/i2c-{bus}" + (f" 0x{addr:02X}" if isinstance(addr, int) else "")
        print(f"I2C 오류 {where}: {e}")
        if e.errno == 16:
            print("  → 이 주소는 커널 드라이버가 점유 중이다(i2cdetect 의 UU). INA228 이 아니라 보드 장치일 가능성.")
        elif e.errno in (5, 6, 121):   # tegra-i2c 는 NACK 를 EIO(5) 로 돌려준다
            print("  → 이 주소에서 아무도 답하지 않는다. 전원·SDA/SCL·GND 배선과 커넥터(IIC0=1, IIC1=7)를 본다.")
        elif e.errno == 110:
            print("  → 버스 자체가 응답이 없다(타임아웃). 미배선 버스이거나 SDA/SCL 이 눌려 있다.")
        sys.exit(2)


if __name__ == "__main__":
    main()
