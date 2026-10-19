"""API do simulador."""
from flask import Blueprint, jsonify, request
from flask_login import current_user
from extensions import db
from models import SimulationResult
from simulation import calculate_simulation
from utils import get_content, student_required
simulator_bp = Blueprint("simulator", __name__)
@simulator_bp.route("/student/simulator")
@student_required
def simulator_view():
    from flask import render_template
    last = SimulationResult.query.filter_by(role_id=current_user.role_id).order_by(SimulationResult.created_at.desc()).first()
    intro = get_content("sim_intro", "Simulador de Decisão", "Configure a matriz energética e veja o impacto nos 4 eixos em tempo real.")
    return render_template("student/simulator.html", last_sim=last, intro=intro)
@simulator_bp.route("/api/simulate", methods=["POST"])
@student_required
def api_simulate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Envie uma configuração válida para a simulação."), 400
    energy_choice = data.get("energy_choice", "thermal")
    if energy_choice not in ("thermal", "hydro"):
        return jsonify(error="Escolha uma matriz energética válida."), 400
    if energy_choice == "thermal" and data.get("fuel_type", "gas") not in ("gas", "coal"):
        return jsonify(error="Escolha um combustível válido."), 400
    relevant_options = (
        ("has_filters",)
        if energy_choice == "thermal"
        else ("has_relocation_plan", "has_fish_ladder")
    )
    for key in relevant_options:
        if key in data and not isinstance(data[key], bool):
            return jsonify(error="As opções de mitigação devem ser booleanas."), 400

    simulation_data = dict(data)
    if energy_choice == "thermal":
        simulation_data.update(has_relocation_plan=False, has_fish_ladder=False)
        simulation_data.pop("dam_height", None)
    else:
        simulation_data.update(has_filters=False, fuel_type="gas")
    result = calculate_simulation(simulation_data)
    row = SimulationResult(role_id=current_user.role_id, energy_choice=result["energy_choice"], has_filters=result["has_filters"], has_relocation_plan=result["has_relocation_plan"], has_fish_ladder=result["has_fish_ladder"], fuel_type=result.get("fuel_type"), dam_height=result.get("dam_height"), env_score=result["env_score"], social_score=result["social_score"], economic_score=result["economic_score"], energy_score=result["energy_score"])
    db.session.add(row); db.session.commit()
    result["id"] = row.id
    return jsonify(result)
