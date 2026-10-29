"""Build explicit screening assumptions, not measured hardware parameters.

The generated declaration names omissions so the native model does not present
a complete source total. Explicit --engineering-estimate additionally labels
the values as estimates, never as measured or complete hardware totals. The
100 kHz small-signal Q estimate combines inductor AC losses, not core alone.
"""
import argparse
import json
import math
from pathlib import Path

TI = "https://www.ti.com/lit/ds/symlink/drv8311.pdf"
TI_LOSS = "https://www.ti.com/document-viewer/DRV8311/datasheet/GUID-C826F7E8-19E5-47C8-9C09-E13912428538"
BOURNS = "https://www.bourns.com/docs/product-datasheets/srp1265wa.pdf"
COILCRAFT_Q = "https://www.coilcraft.com/en-us/resources/application-notes/key-parameters-for-selecting-rf-inductors/"
MU0 = 4 * math.pi * 1e-7


def slab_skin_increment(rho_ohm_m, frequency_hz, thickness_m):
    """Isolated symmetric conducting slab AC/DC R increment; excludes proximity."""
    if not all(math.isfinite(v) and v > 0 for v in (rho_ohm_m, frequency_hz, thickness_m)):
        raise ValueError("Slab inputs must be finite and positive")
    delta = math.sqrt(rho_ohm_m / (math.pi * frequency_hz * MU0))
    a = thickness_m / (2 * delta)
    if a < .01:
        return 4 * a**4 / 45  # leading term avoids cancellation at low f
    return a * (math.sinh(2*a) + math.sin(2*a)) / (math.cosh(2*a) - math.cos(2*a)) - 1


def screening_assumptions(*, voltage, pwm_hz, phase_inductance_h, winding_temp_c,
                          phase_names, driver_path_ohm, external_inductance_h,
                          phase_resistance_ohm, phase_resistances_ohm, copper_thickness_m,
                          electrical_period_m, max_phase_peak_a, max_speed_m_s):
    """50%-duty triangular two-phase RL screening case; SI inputs/outputs.

    At any cycle a uniformly selected phase pair carries +/- triangular ripple,
    the third carries zero. This produces a balanced PSD covariance. It is not
    an actual space-vector PWM waveform or a guaranteed bound for all duties.
    The stated frequency, source and driver assumptions are not generalized.
    """
    if (voltage != 12 or pwm_hz != 100_000 or driver_path_ohm != .21
            or len(phase_names) != 3 or len(set(phase_names)) != 3
            or len(phase_resistances_ohm) != 3
            or external_inductance_h not in (0.0, 47e-6)
            or not all(math.isfinite(v) and v > 0 for v in
                       (phase_inductance_h, phase_resistance_ohm, copper_thickness_m, electrical_period_m,
                        max_phase_peak_a, max_speed_m_s, *phase_resistances_ohm))
            or not math.isfinite(winding_temp_c)):
        raise ValueError("Screening case requires 12 V, 100 kHz, DRV8311 0.21 ohm, three phases and 0 or 47 uH external inductance")

    # Exact steady-state 50%-duty RL half cycles: +/-Vbus/2 on a
    # two-phase loop with Rloop=2 Rphase and Lloop=2 Lphase.
    delta_pp = voltage / (2 * phase_resistance_ohm) * math.tanh(
        phase_resistance_ohm / (4 * pwm_hz * phase_inductance_h))
    pair_variance = delta_pp**2 / 12
    diag = 2 * pair_variance / 3
    cov = [[diag if i == j else -diag / 2 for j in range(3)] for i in range(3)]

    # Bourns SRP1265WA-470M: 47 uH, typical DCR 74.1 mΩ and Q=20
    # at 100 kHz/1 V, 25 °C. Approximate 100 kHz equivalent resistance
    # = omega L / Q. It includes conductor and core loss. Subtract DCR at
    # the SAME 25 °C reference before adding hot DCR separately.
    dcr_25 = .0741 if external_inductance_h else 0.0
    dcr_hot = dcr_25 * (1 + .00393 * (winding_temp_c - 25))
    if dcr_hot < 0:
        raise ValueError("Invalid assumed inductor temperature")
    r_ac_extra = (2 * math.pi * pwm_hz * external_inductance_h / 20 - dcr_25) if external_inductance_h else 0.0
    # A triangular wave's fundamental RMS is sqrt(8)/pi² times its p-p
    # excursion. Only 2/3 of phases carry this ripple in the chosen mixture.
    fundamental_variance = (2 / 3) * (math.sqrt(8) / math.pi**2 * delta_pp)**2
    extra_inductor_w = max(0.0, r_ac_extra) * fundamental_variance

    # Isolated-slab skin effect. Apply the fraction to each complete hot DC
    # network as a screening approximation; vias and proximity are not solved.
    rho_hot = 1.724e-8 * (1 + .00393 * (winding_temp_c - 20))
    fundamental_factor = slab_skin_increment(rho_hot, max_speed_m_s / electrical_period_m, copper_thickness_m)
    ripple_factor = slab_skin_increment(rho_hot, pwm_hz, copper_thickness_m)

    # TI table 12-1 electrical-cycle FOC RMS formulas translated to a
    # per-cycle law proportional to sum(abs(mean phase current)). For ideal
    # balanced sinusoidal currents, average sum(abs(i)) = 6 Ipk/pi and
    # Irms = Ipk/sqrt(2). Assume 20-80% 75 V/us SLEW=01, 200 ns deadtime,
    # and 0.7 V diode drop (explicit engineering assumption, not TI data).
    rise_time = .6 * voltage / 75e6
    switch_coefficient = math.pi / (2 * math.sqrt(2)) * voltage * rise_time
    dead_coefficient = math.pi / math.sqrt(2) * .7 * 200e-9
    # Linear interpolation of TI typical 10 mA @25 kHz and 12 mA @200 kHz.
    internal_current = .010 + (.012 - .010) * ((pwm_hz - 25_000) / 175_000)
    reference = (f"Screening scenario: TI SLVSFN2B {TI} and {TI_LOSS}; "
                 f"Bourns SRP1265WA-470M small-signal Q/DCR {BOURNS}; "
                 f"Q includes conductor and core losses {COILCRAFT_Q}. "
                 "25 C driver, SLEW=01, DEADTIME=001, 0.7 V assumed diode drop; "
                 "electrical-cycle sinusoidal RMS mapping; inductor temperature assumed equal to winding temperature. "
                 "Q excess represented as constant 100 kHz fundamental AC-loss proxy, not separately measured core watts. "
                 f"Isolated copper slab approximation at {copper_thickness_m:.9g} m and {winding_temp_c:.5g} C; "
                 "full phase DC network used as proxy for copper thickness, with electrical fundamental at domain maximum speed. "
                 "No switching waveform, hardware selection or thermal rating inferred.")
    return {
        "basis": "declared_parameters", "reference": reference,
        "domain": {"driver_name": "DRV8311", "source_voltage_v": voltage, "pwm_hz": pwm_hz,
                   "winding_temp_c": winding_temp_c, "driver_path_resistance_ohm": driver_path_ohm,
                   "max_phase_peak_a": max_phase_peak_a, "max_speed_m_s": max_speed_m_s,
                   "geometry": {"phase_resistance_hot_ohm": list(phase_resistances_ohm),
                                "effective_phase_inductance_h": phase_inductance_h,
                                "copper_thickness_m": copper_thickness_m, "electrical_period_m": electrical_period_m}},
        "phase_names": list(phase_names),
        "winding_fundamental_ac_increment_ohm": [r * fundamental_factor for r in phase_resistances_ohm],
        "winding_ripple_ac_increment_ohm": [r * ripple_factor for r in phase_resistances_ohm],
        "external_series_resistance_ohm": [dcr_hot] * 3,
        "external_core_loss_w": [extra_inductor_w] * 3,
        "ripple": {"covariance_a2": cov, "peak_deviation_a": [delta_pp / 2] * 3,
                   "reference": f"50%-duty two-phase RL p-p used as triangular screening mixture; Lphase={phase_inductance_h:.12g} H, Rphase={phase_resistance_ohm:.12g} ohm, pp={delta_pp:.12g} A. Approximate waveform, not actual PWM or a universal envelope."},
        "switching": {"constant_j": 0.0, "abs_mean_current_j_per_a": switch_coefficient, "mean_square_current_j_per_a2": 0.0},
        "deadtime": {"constant_j": 0.0, "abs_mean_current_j_per_a": dead_coefficient, "mean_square_current_j_per_a2": 0.0},
        "controller_power_w": voltage * internal_current, "other_dc_link_power_w": 0.0,
        "omitted_losses": ["Winding proximity and via-specific AC loss not represented by isolated slab approximation",
                           "Inductor AC loss outside 100 kHz fundamental and bias/temperature effects not characterized",
                           "Board-level controller/regulator and source wiring consumption not specified"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON keyword inputs, including per-phase inductance in H")
    parser.add_argument("output", type=Path, help="new loss-model JSON; existing files are never replaced")
    parser.add_argument("--from-native-receipt", action="store_true", help="derive screening inputs from a native saved-design baseline receipt")
    parser.add_argument("--engineering-estimate", action="store_true", help="explicitly label the approximate scenario as an engineering estimate; named exclusions remain")
    args = parser.parse_args()
    raw = json.loads(args.input.read_text())
    if args.from_native_receipt:
        native = raw['native']
        drive, actual = native['result']['drive'], native['inputs']['drive']
        ext = actual['series_inductance_h']
        hot_dcr = .0741 * (1 + .00393 * (actual['winding_temp_c'] - 25)) if ext else 0.0
        # Driver path is one high-side plus one low-side FET across a two-phase
        # loop. Halve it when expressing the loop as two equal phase resistances.
        phase_r = drive['phase_resistance_ohm'] + hot_dcr + actual['driver']['rds_on_ohm'] / 2
        raw = dict(voltage=drive['bus_voltage_v'], pwm_hz=actual['pwm_hz'],
                   phase_inductance_h=drive['effective_inductance_h'],
                   phase_resistance_ohm=phase_r, winding_temp_c=actual['winding_temp_c'],
                   phase_resistances_ohm=[p['resistance_hot_ohm'] for p in drive['phases']],
                   copper_thickness_m=max(drive['outer_copper_m'], drive['inner_copper_m']),
                   electrical_period_m=2 * native['inputs']['config']['magnet_pitch_m'],
                   phase_names=[p['net'] for p in drive['phases']],
                   driver_path_ohm=actual['driver']['rds_on_ohm'], external_inductance_h=ext,
                   # A numerical applicability interval for the screening
                   # formula, never a component rating or operating limit.
                   max_phase_peak_a=20, max_speed_m_s=1)
    result = screening_assumptions(**raw)
    if args.engineering_estimate:
        result['basis'] = 'engineering_estimate'
        result['reference'] += " Explicit engineering estimate: named omitted effects are excluded, not estimated to be exactly zero. This is not a complete hardware total or a bound."
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
