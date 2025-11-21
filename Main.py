# -- coding: utf-8 --
from __future__ import annotations
import os, json, re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from FileChooser import select_file

from Utils.Agents import (
    TriageBalancer,
    SeniorCardiologist,
    NoviceCardiologist,
    SeniorPsychologist,
    NovicePsychologist,
    SeniorPulmonologist,
    NovicePulmonologist,
    MultidisciplinaryTeam,
)

# =========================
# Configuração de paths
# =========================
BASE_DIR     = Path(__file__).parent
REPORTS_DIR  = BASE_DIR / "Medical Reports"
RESULTS_DIR  = BASE_DIR / "Results"
RESULTS_DIR.mkdir(exist_ok=True)

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

def run_single_report(path: Path | None = None):
    # Se não foi fornecido path, abre o FileChooser para o utilizador selecionar
    if path is None:
        selecionado = select_file()
        if not selecionado:
            print("Nenhum ficheiro selecionado. A cancelar.")
            return
        path = Path(selecionado)

    # Lê o relatório
    medical_report = path.read_text(encoding="utf-8", errors="ignore")
    patient_name   = extract_patient_name_from_filename(path)
 
    # 1) Run triage to decide which specialists to invoke
    triage_agent = TriageBalancer(medical_report)
    triage_response = triage_agent.run()
    selected_specialties = {"Cardiology": False, "Psychology": False, "Pulmonology": False}
    run_all_specialists = False
 
    # Try to parse triage JSON robustly
    if triage_response:
        try:
            triage_obj = json.loads(triage_response)
        except Exception:
            # Try to extract JSON substring if extra text is present
            m = re.search(r'(\{.*\})', str(triage_response), re.S)
            if m:
                try:
                    triage_obj = json.loads(m.group(1))
                except Exception:
                    triage_obj = None
            else:
                triage_obj = None
        if isinstance(triage_obj, dict):
            def get_weight(key):
                try:
                    v = triage_obj.get(key, {}).get("weight")
                    return int(v)
                except Exception:
                    # fallback: try to parse numbers from strings
                    try:
                        return int(re.search(r'(\d+)', str(triage_obj.get(key, {}))).group(1))
                    except Exception:
                        return None
 
            cardio_w = get_weight("Cardiology")
            psych_w  = get_weight("Psychology")
            pulmon_w = get_weight("Pulmonology")
 
            threshold = int(os.getenv("TRIAGE_THRESHOLD", "3"))
            if cardio_w is not None and cardio_w >= threshold:
                selected_specialties["Cardiology"] = True
            if psych_w is not None and psych_w >= threshold:
                selected_specialties["Psychology"] = True
            if pulmon_w is not None and pulmon_w >= threshold:
                selected_specialties["Pulmonology"] = True
            # If none selected (e.g., low scores), still run all as fallback
            if not any(selected_specialties.values()):
                run_all_specialists = True
        else:
            run_all_specialists = True
    else:
        run_all_specialists = True
 
    # 2) Instantiate chosen specialist agents
    agents = {}


    #* If all specialists are to be run, instantiate just senior agents due to resource constraints
    if run_all_specialists:
        agents["Senior_Cardiologist"] = SeniorCardiologist(medical_report)
        agents["Senior_Psychologist"] = SeniorPsychologist(medical_report)
        agents["Senior_Pulmonologist"] = SeniorPulmonologist(medical_report)
    else:
        if selected_specialties.get("Cardiology"):
            agents["Senior_Cardiologist"] = SeniorCardiologist(medical_report)
            agents["Novice_Cardiologist"] = NoviceCardiologist(medical_report)
        if selected_specialties.get("Psychology"):
            agents["Senior_Psychologist"] = SeniorPsychologist(medical_report)
            agents["Novice_Psychologist"] = NovicePsychologist(medical_report)
        if selected_specialties.get("Pulmonology"):
            agents["Senior_Pulmonologist"] = SeniorPulmonologist(medical_report)
            agents["Novice_Pulmonologist"] = NovicePulmonologist(medical_report)
 
    # Save triage response in the responses dict for traceability
    responses = {"Triage": triage_response}
 
    # Run specialist agents in parallel and collect outputs
    def get_response(agent_name, agent):
        return agent_name, agent.run()
 
    with ThreadPoolExecutor(max_workers=max(1, len(agents))) as executor:
        futures = {executor.submit(get_response, name, ag): name for name, ag in agents.items()}
        for fut in as_completed(futures):
            name, resp = fut.result()
            responses[name] = resp
 
        # Agente de equipa multidisciplinar (igual ao teu fluxo)
        team_agent = MultidisciplinaryTeam(
            cardiologist_report  = responses.get("Senior_Cardiologist", "") + responses.get("Novice_Cardiologist", ""),
            psychologist_report  = responses.get("Senior_Psychologist", "") + responses.get("Novice_Psychologist", ""),
            pulmonologist_report = responses.get("Senior_Pulmonologist", "") + responses.get("Novice_Pulmonologist", ""),
        )
        final_diagnosis3 = team_agent.run()
 
        # Guarda TXT e JSON com timestamp + nome do paciente
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_name = f"{patient_name}_diagnosis{ts}"
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
        print(f" Nenhum .txt encontrado em: {REPORTS_DIR}")
        return
    print(f" Encontrados {len(files)} relatórios. A processar...\n")
    for p in files:
        try:
            run_single_report(p)
        except Exception as e:
            print(f"✖ Erro em {p.name}: {e}")

if __name__ == "__main__":
    # Abre o seletor para escolher um ficheiro quando executar diretamente
    run_single_report()
    # process_all_reports()
