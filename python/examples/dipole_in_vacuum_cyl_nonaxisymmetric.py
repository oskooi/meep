"""Radiation pattern of a nonaxisymmetric dipole in cylindrical coordinates."""

import argparse
import math
from typing import Tuple

import matplotlib.pyplot as plt
import meep as mp
import numpy as np


RESOLUTION_UM = 50
WAVELENGTH_UM = 1.0
PML_UM = 1.0
FARFIELD_RADIUS_UM = 1e6 * WAVELENGTH_UM
NUM_FARFIELD_PTS = 50
POWER_DECAY_THRESHOLD = 1e-4
DEBUG_OUTPUT = True

frequency = 1 / WAVELENGTH_UM
polar_rad = np.linspace(0, 0.5 * math.pi, NUM_FARFIELD_PTS)


def plot_radiation_pattern(radial_flux: np.ndarray):
    """Plots the radiation pattern in polar coordinates.

    The angles increase clockwise with zero in the +z direction (the "pole")
    and π/2 in the +r direction (the "equator").

    Args:
        radial_flux: the radial flux in polar coordinates.
    """
    normalized_radial_flux = radial_flux / np.max(radial_flux)
    dipole_radial_flux = np.square(np.cos(polar_rad))

    fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(6, 6))
    ax.plot(polar_rad, normalized_radial_flux, "b-", label="Meep")
    ax.plot(polar_rad, dipole_radial_flux, "r-", label="$\cos^2θ$")
    ax.legend()
    ax.set_theta_direction(-1)
    ax.set_theta_offset(0.5 * math.pi)
    ax.set_thetalim(0, 0.5 * math.pi)
    ax.set_rmax(1)
    ax.set_rticks([0, 0.5, 1])
    ax.grid(True)
    ax.set_rlabel_position(22)
    ax.set_ylabel("radial flux (a.u.)")
    ax.set_title("radiation pattern of a nonaxisymmetric $E_r$ dipole")

    if mp.am_master():
        fig.savefig(
            "dipole_radiation_pattern_nonaxisymmetric.png",
            dpi=100,
            bbox_inches="tight",
        )

    relative_error = (
        np.linalg.norm(normalized_radial_flux - dipole_radial_flux) /
        np.linalg.norm(dipole_radial_flux)
    )
    print(f"relative error in radiation pattern:, {relative_error}")


def radiation_pattern(e_field: np.ndarray, h_field: np.ndarray) -> np.ndarray:
    """Computes the radiation pattern from the far fields.

    Args:
        e_field, h_field: the electric (Er, Ep, Ez) and magnetic (Hr, Hp, Hz)
          far fields, respectively.

    Returns:
        The radial Poynting flux as a 1D array. One element for each point on
        the circumference of a quarter circle with angular range of
        [0, π/2] rad. 0 radians is the +z direction (the "pole") and π/2 is
        the +r direction (the "equator").
    """
    flux_x = np.real(e_field[:, 1] * h_field[:, 2] -
                     e_field[:, 2] * h_field[:, 1])
    flux_z = np.real(e_field[:, 0] * h_field[:, 1] -
                     e_field[:, 1] * h_field[:, 0])
    flux_r = np.sqrt(np.square(flux_x) + np.square(flux_z))

    return flux_r


def get_farfields(
        sim: mp.Simulation,
        n2f_mon: mp.DftNear2Far
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes the far fields from the near fields.

    Args:
        sim: a `Simulation` object.
        n2f_mon: a `DftNear2Far` object returned by `Simulation.add_near2far`.

    Returns:
        The electric (Er, Ep, Ez) and magnetic (Hr, Hp, Hz) far fields. One row
        with six columns for the fields for each point on the circumference of
        a quarter circle with angular range of [0, π/2] rad. 0 radians is the
        +z direction (the "pole") and π/2 is the +r direction (the "equator").
    """
    e_field = np.zeros((NUM_FARFIELD_PTS, 3), dtype=np.complex128)
    h_field = np.zeros((NUM_FARFIELD_PTS, 3), dtype=np.complex128)
    for n in range(NUM_FARFIELD_PTS):
        far_field = sim.get_farfield(
            n2f_mon,
            mp.Vector3(
                FARFIELD_RADIUS_UM * math.sin(polar_rad[n]),
                0,
                FARFIELD_RADIUS_UM * math.cos(polar_rad[n])
            )
        )
        e_field[n, :] = [np.conj(far_field[j]) for j in range(3)]
        h_field[n, :] = [far_field[j + 3] for j in range(3)]

    return e_field, h_field


def dipole_in_vacuum(
        dipole_pos_r: mp.Vector3,
        m: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes the far fields of a nonaxisymmetric point source.

    Args:
        dipole_pos_r: the radial position of the dipole.
        m: angular φ dependence of the fields exp(imφ).

    Returns:
        A 2-tuple containing the electric and magnetic far fields as 1D arrays.
    """
    sr = 2.0
    sz = 4.0
    cell_size = mp.Vector3(sr + PML_UM, 0, sz + 2 * PML_UM)

    boundary_layers = [mp.PML(thickness=PML_UM)]

    sources = [
        mp.Source(
            src=mp.GaussianSource(frequency, fwidth=0.1 * frequency),
            component=mp.Er,
            center=mp.Vector3(dipole_pos_r, 0, 0)
        )
    ]

    sim = mp.Simulation(
        resolution=RESOLUTION_UM,
        cell_size=cell_size,
        dimensions=mp.CYLINDRICAL,
        m=m,
        boundary_layers=boundary_layers,
        sources=sources,
        force_complex_fields=True
    )

    nearfields_monitor = sim.add_near2far(
        frequency,
        0,
        1,
        mp.FluxRegion(
            center=mp.Vector3(0.5 * sr, 0, 0.5 * sz),
            size=mp.Vector3(sr, 0, 0)
        ),
        mp.FluxRegion(
            center=mp.Vector3(sr, 0, 0),
            size=mp.Vector3(0, 0, sz)
        ),
        mp.FluxRegion(
            center=mp.Vector3(0.5 * sr, 0, -0.5 * sz),
            size=mp.Vector3(sr, 0, 0),
            weight=-1.0
        )
    )

    sim.run(
        until_after_sources=mp.stop_when_fields_decayed(
            20.0, mp.Er, mp.Vector3(dipole_pos_r, 0, 0), 1e-6
        )
    )

    if DEBUG_OUTPUT:
        fig, ax = plt.subplots()
        sim.plot2D(ax=ax, show_monitors=True)
        if mp.am_master():
            fig.savefig(
                "dipole_in_vacuum_cyl_layout.png",
                dpi=150,
                bbox_inches="tight"
            )

    e_field, h_field = get_farfields(sim, nearfields_monitor)

    return e_field, h_field


def flux_from_farfields(e_field: np.ndarray, h_field: np.ndarray) -> float:
    """Computes the flux from the far fields.

    Args:
        e_field, h_field: the electric (Er, Ep, Ez) and magnetic (Hr, Hp, Hz)
          far fields, respectively.

    Returns:
        The Poynting flux obtained from the far fields.
    """
    dphi = 2 * math.pi
    dtheta = 0.5 * math.pi / (NUM_FARFIELD_PTS - 1)
    dipole_radiation_pattern = radiation_pattern(e_field, h_field)
    flux = (
        np.sum(dipole_radiation_pattern * np.sin(polar_rad)) *
        FARFIELD_RADIUS_UM**2 *
        dtheta *
        dphi
    )

    return flux


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dipole_pos_r",
        type=float,
        help="radial position of the dipole"
    )
    args = parser.parse_args()

    # Fourier series expansion of the fields from a ring current source
    # used to generate a point dipole localized in the azimuthal direction.

    e_field_total = np.zeros((NUM_FARFIELD_PTS, 3), dtype=np.complex128)
    h_field_total = np.zeros((NUM_FARFIELD_PTS, 3), dtype=np.complex128)
    flux_max = 0
    m = 0
    while True:
        e_field, h_field = dipole_in_vacuum(args.dipole_pos_r, m)
        e_field_total += e_field
        h_field_total += h_field

        if m > 0:
            e_field, h_field = dipole_in_vacuum(args.dipole_pos_r, -m)
            e_field_total += e_field
            h_field_total += h_field

        flux = flux_from_farfields(e_field, h_field)
        if flux > flux_max:
            flux_max = flux
        power_decay = flux / flux_max
        print(f"power_decay:, {m}, {flux}, {flux_max}, {power_decay}")

        if m > 0 and power_decay < POWER_DECAY_THRESHOLD:
            break
        else:
            m += 1

    dipole_radiation_pattern = radiation_pattern(
        e_field_total, h_field_total
    )
    dipole_radiation_pattern_scaled = (
        dipole_radiation_pattern * FARFIELD_RADIUS_UM**2
    )
    plot_radiation_pattern(dipole_radiation_pattern_scaled)

    if mp.am_master():
        np.savez(
            "dipole_farfields_nonaxisymmetric.npz",
            FARFIELD_RADIUS_UM=FARFIELD_RADIUS_UM,
            PML_UM=PML_UM,
            POWER_DECAY_THRESHOLD=POWER_DECAY_THRESHOLD,
            RESOLUTION_UM=RESOLUTION_UM,
            WAVELENGTH_UM=WAVELENGTH_UM,
            dipole_pos_r=args.dipole_pos_r,
            dipole_radiation_pattern=dipole_radiation_pattern,
            e_field_total=e_field_total,
            h_field_total=h_field_total,
            m=m,
            polar_rad=polar_rad,
        )