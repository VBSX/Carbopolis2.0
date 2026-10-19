from utils import clamp, get_sim_vars


def _var(vars_map, key, fallback):
    value = vars_map.get(key)
    return fallback if value is None else value


def calculate_simulation(payload):
    """Calcula os quatro eixos do dilema energético de Ivaí dos Campos."""
    v = get_sim_vars()

    energy_choice = payload.get("energy_choice") or "thermal"
    has_filters = bool(payload.get("has_filters"))
    has_relocation = bool(payload.get("has_relocation_plan"))
    has_fish_ladder = bool(payload.get("has_fish_ladder"))
    fuel_type = payload.get("fuel_type") or "gas"
    try:
        dam_height = float(payload.get("dam_height") or 40)
    except (TypeError, ValueError):
        dam_height = 40.0
    dam_height = clamp(dam_height, 10.0, 100.0)

    so2_gas = _var(v, "so2_gas_base", 45.0)
    nox_gas = _var(v, "nox_gas_base", 55.0)
    co2_gas = _var(v, "co2_gas_base", 68.0)
    so2_coal = _var(v, "so2_coal_base", 180.0)
    nox_coal = _var(v, "nox_coal_base", 125.0)
    co2_coal = _var(v, "co2_coal_base", 98.0)
    filter_reduction = _var(v, "filter_so2_nox_reduction", 0.70)
    filter_cost = _var(v, "filter_cost", 18.0)
    fish_ladder_cost = _var(v, "fish_ladder_cost", 10.0)
    relocation_cost = _var(v, "relocation_cost", 16.0)
    flood_per_meter = _var(v, "flooded_area_percent_per_meter", 0.35)
    families_per_pct = _var(v, "families_per_flood_percent", 4.2)
    mw_per_meter = _var(v, "mw_per_dam_meter", 2.4)
    thermal_mw = _var(v, "thermal_base_mw", 180.0)
    hydro_build_penalty = _var(v, "hydro_build_time_penalty", 22.0)
    thermal_jobs = _var(v, "thermal_jobs", 28.0)
    hydro_jobs = _var(v, "hydro_jobs", 42.0)
    royalty_thermal = _var(v, "royalty_thermal", 22.0)
    royalty_hydro = _var(v, "royalty_hydro", 30.0)
    health_weight = _var(v, "health_emission_weight", 0.18)
    fauna_penalty = _var(v, "aquatic_fauna_penalty", 18.0)
    mixed_thermal_share = _var(v, "mixed_thermal_share", 0.45)

    if fuel_type == "coal":
        so2, nox, co2 = so2_coal, nox_coal, co2_coal
    else:
        so2, nox, co2 = so2_gas, nox_gas, co2_gas

    if has_filters:
        so2 *= 1.0 - filter_reduction
        nox *= 1.0 - filter_reduction

    flooded_pct = dam_height * flood_per_meter
    families = flooded_pct * families_per_pct
    hydro_mw = dam_height * mw_per_meter

    if energy_choice == "thermal":
        thermal_share, hydro_share = 1.0, 0.0
        mw = thermal_mw
    elif energy_choice == "hydro":
        thermal_share, hydro_share = 0.0, 1.0
        mw = hydro_mw
        so2, nox, co2 = so2 * 0.08, nox * 0.08, co2 * 0.12
    else:
        thermal_share, hydro_share = mixed_thermal_share, 1.0 - mixed_thermal_share
        mw = thermal_mw * thermal_share + hydro_mw * hydro_share
        so2 = so2 * thermal_share + so2 * 0.08 * hydro_share
        nox = nox * thermal_share + nox * 0.08 * hydro_share
        co2 = co2 * thermal_share + co2 * 0.12 * hydro_share

    flood_used = flooded_pct * hydro_share
    families_used = families * hydro_share
    if has_relocation:
        families_used *= 0.35

    fauna_hit = fauna_penalty * hydro_share
    if has_fish_ladder:
        fauna_hit *= 0.4

    env = 100.0
    env -= so2 * 0.18
    env -= nox * 0.16
    env -= co2 * 0.12
    env -= flood_used * 0.9
    env -= fauna_hit
    env = clamp(env)

    jobs = thermal_jobs * thermal_share + hydro_jobs * hydro_share
    health_hit = (so2 + nox) * health_weight
    protest = 22.0 * hydro_share
    if has_relocation:
        protest *= 0.3
    social = 52.0 + jobs * 0.55 - families_used * 0.35 - health_hit - protest
    social = clamp(social)

    mitigation_cost = 0.0
    if has_filters and thermal_share > 0:
        mitigation_cost += filter_cost * thermal_share
    if has_fish_ladder and hydro_share > 0:
        mitigation_cost += fish_ladder_cost * hydro_share
    if has_relocation and hydro_share > 0:
        mitigation_cost += relocation_cost * hydro_share

    royalties = royalty_thermal * thermal_share + royalty_hydro * hydro_share
    capex_penalty = 8.0 * thermal_share + 20.0 * hydro_share + dam_height * 0.08 * hydro_share
    economic = 48.0 + royalties + mw * 0.08 - mitigation_cost - capex_penalty
    economic = clamp(economic)

    build_speed = 88.0 * thermal_share + (70.0 - hydro_build_penalty) * hydro_share
    continuity = 62.0 * thermal_share + (78.0 + dam_height * 0.12) * hydro_share
    if energy_choice == "mixed":
        continuity += 8.0
    energy = clamp((build_speed * 0.45 + continuity * 0.55))

    return {
        "energy_choice": energy_choice,
        "has_filters": has_filters,
        "has_relocation_plan": has_relocation,
        "has_fish_ladder": has_fish_ladder,
        "fuel_type": fuel_type,
        "dam_height": round(dam_height, 1),
        "so2_ppm": round(so2, 1),
        "nox_ppm": round(nox, 1),
        "co2_ppm": round(co2, 1),
        "flooded_area_percent": round(flood_used, 1),
        "families_displaced": round(families_used, 0),
        "power_mw": round(mw, 1),
        "env_score": round(env, 1),
        "social_score": round(social, 1),
        "economic_score": round(economic, 1),
        "energy_score": round(energy, 1),
    }
