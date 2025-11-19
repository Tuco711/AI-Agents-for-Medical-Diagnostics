# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Agentes do teu projeto
from Utils.Agents import Cardiologist, Psychologist, Pulmonologist, MultidisciplinaryTeam

<<<<<<< HEAD
# =========================
# Configuração de paths
# =========================
BASE_DIR     = Path(__file__).parent
REPORTS_DIR  = BASE_DIR / "Medical Reports"
RESULTS_DIR  = BASE_DIR / "Results"
RESULTS_DIR.mkdir(exist_ok=True)
=======
# read the medical report
with open("Medical Reports\Medical Rerort - Michael Johnson - Panic Attack Disorder.txt", "r", encoding="utf-8") as file:
    medical_report = file.read()
>>>>>>> 084c1363a24b59a94dc770c45f8770bb938a83ea

# =========================
# ENV
# =========================
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")  # é usado internamente pelos agentes
if not API_KEY:
    print("Falta OPENROUTER_API_KEY no .env")
    # não faço exit para poderes ver o aviso

# =========================
# Helpers
# =========================
def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()

def extract_patient_name_from_filename(path: Path) -> str:
    """
    Tenta apanhar o nome do paciente de nomes tipo:
    'Medical Report - John Doe - Panic Attack ... .txt'
    ou mesmo com o teu ficheiro 'Medical Rerort - ...'
    """
    parts = path.stem.split(" - ")
    if len(parts) >= 2:
        return sanitize_filename(parts[1])
    return sanitize_filename(path.stem)

def run_single_report(path: Path):
    # Lê o relatório
    medical_report = path.read_text(encoding="utf-8", errors="ignore")
    patient_name   = extract_patient_name_from_filename(path)

    # Instancia agentes com o texto do relatório (igual ao teu código)
    agents = {
        "Cardiologist":  Cardiologist(medical_report),
        "Psychologist":  Psychologist(medical_report),
        "Pulmonologist": Pulmonologist(medical_report),
    }

<<<<<<< HEAD
    # Corre agentes em paralelo e recolhe respostas
    def get_response(agent_name, agent):
        return agent_name, agent.run()
=======
# Run the MultidisciplinaryTeam agent to generate the final diagnosis
final_diagnosis = team_agent.run()
final_diagnosis_text = "### Final Diagnosis:\n\n" + final_diagnosis
# Save inside the project's Results directory next to this script
base_dir = os.path.dirname(os.path.abspath(__file__))
txt_output_path = os.path.join(base_dir, "Results", "final_diagnosis_Michel_Johnson.txt")
>>>>>>> 084c1363a24b59a94dc770c45f8770bb938a83ea

    responses = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = {executor.submit(get_response, name, ag): name for name, ag in agents.items()}
        for fut in as_completed(futures):
            name, resp = fut.result()
            responses[name] = resp

    # Agente de equipa multidisciplinar (igual ao teu fluxo)
    team_agent = MultidisciplinaryTeam(
        cardiologist_report  = responses["Cardiologist"],
        psychologist_report  = responses["Psychologist"],
        pulmonologist_report = responses["Pulmonologist"],
    )
    final_diagnosis3 = team_agent.run()

    # Guarda TXT e JSON com timestamp + nome do paciente
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{patient_name}__diagnosis_{ts}"
    txt_output = RESULTS_DIR / f"{base_name}.txt"
    json_output = RESULTS_DIR / f"{base_name}.json"

    txt_output.write_text(
        "### Final Diagnosis\n\n" + str(final_diagnosis3),
        encoding="utf-8"
    )

    payload = {
        "patient_name": patient_name,
        "timestamp": ts,
        "agents": responses,
        "final_diagnosis": final_diagnosis3,
        "meta": {
            "model": os.getenv("OPENROUTER_MODEL", ""),
            "source_file": path.name,
        },
    }
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✔ {path.name} → guardado:\n   - {txt_output.name}\n   - {json_output.name}")

def process_all_reports():
    files = sorted(p for p in REPORTS_DIR.glob("*.txt") if p.is_file())
    if not files:
        print(f"⚠️  Nenhum .txt encontrado em: {REPORTS_DIR}")
        return
    print(f"🔎 Encontrados {len(files)} relatórios. A processar...\n")
    for p in files:
        try:
            run_single_report(p)
        except Exception as e:
            print(f"✖ Erro em {p.name}: {e}")

if __name__ == "__main__":
    process_all_reports()
