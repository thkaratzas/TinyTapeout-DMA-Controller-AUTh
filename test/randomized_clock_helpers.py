# SPDX-FileCopyrightText: © 2026 Zisis Katsaros
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer


def _random_even_period_ps(rng, nominal_ps, span_percent=20):
    low_scale = 1 - span_percent / 100
    high_scale = 1 + span_percent / 100
    period = int(nominal_ps * rng.uniform(low_scale, high_scale))
    return max(2, period - (period % 2))


async def _start_clock_with_phase(signal, period_ps, phase_ps):
    if phase_ps != 0:
        pos_phase_ps = phase_ps if phase_ps > 0 else period_ps + phase_ps
        await Timer(pos_phase_ps, unit="ps")
    clock = Clock(signal, period_ps, unit="ps")
    await clock.start()


async def _init_random_clocks(dut, rng, span_percent=20):
    # Randomize each domain around nominal values with practical margins.
    dmac_period = _random_even_period_ps(rng, 10_000_000, span_percent)
    mem_period = _random_even_period_ps(rng, 12_500_000, span_percent)
    io_period = _random_even_period_ps(rng, 8_330_000, span_percent)

    # Random startup phase offsets create inter-domain phase differences.
    dmac_phase = 0
    mem_phase = rng.randint(0, max(mem_period - 1, 0))
    io_phase = rng.randint(0, max(io_period - 1, 0))

    dut.clk.value = 0
    dut.mem_clk.value = 0
    dut.io_clk.value = 0

    cocotb.start_soon(_start_clock_with_phase(dut.clk, dmac_period, dmac_phase))
    cocotb.start_soon(_start_clock_with_phase(dut.mem_clk, mem_period, mem_phase))
    cocotb.start_soon(_start_clock_with_phase(dut.io_clk, io_period, io_phase))

    # Ensure all three clocks are running before reset/transactions begin.
    await ClockCycles(dut.clk, 3)
