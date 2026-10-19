let chart = null;

const energyChoice = document.getElementById("energy_choice");
const thermalControls = document.getElementById("thermal-controls");
const hydroControls = document.getElementById("hydro-controls");
const output = document.getElementById("simOut");

function setControlsVisible(group, visible) {
  group.hidden = !visible;
  group.style.display = visible ? "block" : "none";
  group.querySelectorAll("input, select").forEach((control) => {
    control.disabled = !visible;
  });
}

function updateControls() {
  const isThermal = energyChoice.value === "thermal";
  setControlsVisible(thermalControls, isThermal);
  setControlsVisible(hydroControls, !isThermal);
}

energyChoice.addEventListener("change", updateControls);
document.getElementById("dam_height").addEventListener("input", (event) => {
  document.getElementById("damLabel").textContent = event.target.value;
});
updateControls();

async function simulate() {
  const choice = energyChoice.value;
  const payload = { energy_choice: choice };
  if (choice === "thermal") {
    payload.has_filters = document.getElementById("has_filters").checked;
    payload.fuel_type = document.getElementById("fuel_type").value;
  } else {
    payload.has_fish_ladder = document.getElementById("has_fish_ladder").checked;
    payload.has_relocation_plan = document.getElementById("has_relocation_plan").checked;
    payload.dam_height = Number(document.getElementById("dam_height").value);
  }

  try {
    const response = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Não foi possível calcular este cenário.");
    }

    const impactDetails = choice === "thermal"
      ? `SO<sub>2</sub> ${result.so2_ppm} ppm | NO<sub>x</sub> ${result.nox_ppm} ppm | CO<sub>2</sub> ${result.co2_ppm} ppm`
      : `Área alagada ${result.flooded_area_percent}% | ${result.families_displaced} famílias afetadas`;
    output.innerHTML = `<b>Resultado da proposta selecionada:</b><br>🌿 Ambiental ${result.env_score} | 🤝 Social ${result.social_score} | 💰 Econômico ${result.economic_score} | ⚡ Energia ${result.energy_score}<br>${impactDetails} | ${result.power_mw} MW`;

    if (chart) {
      chart.destroy();
    }
    chart = new Chart(document.getElementById("radar"), {
      type: "radar",
      data: {
        labels: ["Ambiental", "Social", "Econômico", "Energético"],
        datasets: [{
          label: `Índices — ${choice === "thermal" ? "TermoBR" : "HydroSul"}`,
          data: [result.env_score, result.social_score, result.economic_score, result.energy_score],
          backgroundColor: "rgba(56, 189, 248, 0.25)",
          borderColor: "#38bdf8",
          borderWidth: 2,
          pointBackgroundColor: "#38bdf8",
          pointBorderColor: "#0b1a33",
          pointRadius: 4,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#e2e8f0", font: { size: 12 } } },
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            ticks: { display: false },
            pointLabels: {
              color: "#38bdf8",
              font: { size: 13, weight: "bold", family: "sans-serif" },
            },
            grid: { color: "rgba(255, 255, 255, 0.15)" },
            angleLines: { color: "rgba(255, 255, 255, 0.25)" },
            backgroundColor: "transparent",
          },
        },
      },
    });
  } catch (error) {
    output.textContent = error.message;
  }
}
