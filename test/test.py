# SPDX-FileCopyrightText: © 2026 Zisis Katsaros
# SPDX-License-Identifier: Apache-2.0

import cocotb
import random
from itertools import product
from cocotb.triggers import ClockCycles
from general_test_helpers import (
    _init_clock,
    _reset_dut,
    _run_transfer_sequence,
    _send_cfg,
    _wait_until,
)
from randomized_clock_helpers import _init_random_clocks
from speed_profile_helpers import _init_variable_clocks, _period_from_speed
from timeout_helpers import (
    _timeout_in_receive,
    _timeout_in_sendaddr,
    _timeout_in_senddata,
)



# For all tests
rtrn_delay = 3

# !!! IMPORTANT !!!: set timeout_limit same as the localparam on project.v
timeout_limit = 12
# !!!!!!!!!!!!!!!!!

    # explanation: Internal signals are not visible after synthesis so even if tests pass, during gds check tests that relay on internal 
    # signals will through an error

# Single Word Mode Test
@cocotb.test()
async def test_single_word_mode(dut):
    await _init_clock(dut)
    await _reset_dut(dut)

    src_addr = 0x34
    dst_addr = 0xA1
    payload = [0x5C]

    await _send_cfg(dut, mode=0, direction=0, src_addr=src_addr, dst_addr=dst_addr)
    await _run_transfer_sequence(dut, src_addr=src_addr, dst_addr=dst_addr, payload=payload, direction=0, rtrn_delay=rtrn_delay)

    await _wait_until(dut, lambda: int(dut.uo_out.value[5]) == 1, max_cycles=200)
    await _wait_until(dut, lambda: int(dut.uo_out.value[7]) == 0, max_cycles=40)

# Four Word Burst Mode Test
@cocotb.test()
async def test_burst4_mode(dut):
    await _init_clock(dut)
    await _reset_dut(dut)

    src_addr = 0x20
    dst_addr = 0x80
    payload = [0x11, 0x22, 0x33, 0x44]

    await _send_cfg(dut, mode=1, direction=0, src_addr=src_addr, dst_addr=dst_addr)
    await _run_transfer_sequence(dut, src_addr=src_addr, dst_addr=dst_addr, payload=payload, direction=0, rtrn_delay=rtrn_delay)

    await _wait_until(dut, lambda: int(dut.uo_out.value[5]) == 1, max_cycles=300)
    await _wait_until(dut, lambda: int(dut.uo_out.value[7]) == 0, max_cycles=120)

# Clock domains with randomized frequencies and starting phases stress test
@cocotb.test()
async def test_randomized_clock_and_transfer_stress(dut):
    rng = random.Random()
    span_percent = 20  # frequency variation
    await _init_random_clocks(dut, rng, span_percent)

    for _ in range(100):
        await _reset_dut(dut)

        mode = rng.randint(0, 1)
        direction = rng.randint(0, 1)
        src_addr = rng.randint(0, 0xFF)
        dst_addr = rng.randint(0, 0xFF)
        payload_len = 4 if mode == 1 else 1
        payload = [rng.randint(0, 0xFF) for _ in range(payload_len)]

        await _send_cfg(
            dut,
            mode=mode,
            direction=direction,
            src_addr=src_addr,
            dst_addr=dst_addr,
        )
        await _run_transfer_sequence(
            dut,
            src_addr=src_addr,
            dst_addr=dst_addr,
            payload=payload,
            direction=direction,
            phase_wait_cycles=800,
            rtrn_delay=rtrn_delay
        )

        await _wait_until(dut, lambda: int(dut.uo_out.value[5]) == 1, max_cycles=400)
        await _wait_until(dut, lambda: int(dut.uo_out.value[7]) == 0, max_cycles=160)


# Slow, Normal, Fast speed profiles combionation test
@cocotb.test()
async def test_all_speed_profile_combinations(dut):
    rng = random.Random(0xA11C0B0)

    # Normal periods (ps): DMAC=10us, mem=12.5us, io=8.33us
    dmac_normal_ps = 10_000_000
    mem_normal_ps = 12_500_000
    io_normal_ps = 8_330_000

    # Single variable controlling slow/fast offset from normal.
    speed_delta_percent = 30

    dmac_ref, mem_ref, io_ref = await _init_variable_clocks(
        dut,
        rng,
        dmac_normal_ps,
        mem_normal_ps,
        io_normal_ps,
    )

    speed_levels = ("slow", "normal", "fast")

    for dmac_speed, src_speed, dest_speed in product(speed_levels, repeat=3):
        direction = rng.randint(0, 1)
        mode = rng.randint(0, 1)
        src_addr = rng.randint(0, 0xFF)
        dst_addr = rng.randint(0, 0xFF)
        payload_len = 4 if mode == 1 else 1
        payload = [rng.randint(0, 0xFF) for _ in range(payload_len)]

        # Map logical src/dest speeds to physical mem/io clocks via direction.
        if direction == 0:
            mem_speed = src_speed
            io_speed = dest_speed
        else:
            mem_speed = dest_speed
            io_speed = src_speed

        dmac_ref["period_ps"] = _period_from_speed(dmac_normal_ps, dmac_speed, speed_delta_percent)
        mem_ref["period_ps"] = _period_from_speed(mem_normal_ps, mem_speed, speed_delta_percent)
        io_ref["period_ps"] = _period_from_speed(io_normal_ps, io_speed, speed_delta_percent)

        # Let period updates take effect before reset and transaction.
        await ClockCycles(dut.clk, 4)
        await _reset_dut(dut)

        try:
            await _send_cfg(
                dut,
                mode=mode,
                direction=direction,
                src_addr=src_addr,
                dst_addr=dst_addr,
            )
            await _run_transfer_sequence(
                dut,
                src_addr=src_addr,
                dst_addr=dst_addr,
                payload=payload,
                direction=direction,
                phase_wait_cycles=1200,
                rtrn_delay=rtrn_delay
            )
            await _wait_until(dut, lambda: int(dut.uo_out.value[5]) == 1, max_cycles=600)
            await _wait_until(dut, lambda: int(dut.uo_out.value[7]) == 0, max_cycles=240)
        except AssertionError as exc:
            raise AssertionError(
                "Speed profile failure: "
                f"dmac={dmac_speed}, src={src_speed}, dest={dest_speed}, "
                f"direction={direction}, mode={mode}, "
                f"src_addr=0x{src_addr:02X}, dst_addr=0x{dst_addr:02X}, payload={payload}; {exc}"
            ) from exc

# Timeout test
@cocotb.test()
async def test_return_wait_timeouts(dut, timeout_limit=timeout_limit):
    await _init_clock(dut)

    src_addr = 0x34
    dst_addr = 0xA1
    payload = [0x5C]

    await _timeout_in_receive(dut, src_addr, dst_addr, timeout_limit)
    await _timeout_in_sendaddr(dut, src_addr, dst_addr, payload, rtrn_delay, timeout_limit)
    await _timeout_in_senddata(dut, src_addr, dst_addr, payload, rtrn_delay, timeout_limit)
