import os
import sys
import io
from google import genai
import re
import json

try:
    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass
# Ensure stdout is configured to UTF-8 to avoid Windows cp1252 encoding errors
try:
    # Python 3.7+ has reconfigure
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    # Fallback: wrap the buffer with a UTF-8 text wrapper
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        # Last resort: leave stdout as-is; prints may still fail on some characters
        pass
from langchain_core.prompts import PromptTemplate
from openai import OpenAI

def strip_triple_backticks(text: str) -> str:
    """Remove surrounding triple-backtick fences like ```json or ``` from model output.

    Examples it handles:
    ```json\n{...}\n```  -> {...}
    ```\ntext\n```      -> text
    """
    if not isinstance(text, str):
        return text
    # Remove leading fence like ``` or ```json (possible whitespace before)
    text = re.sub(r'^\s*```(?:\w+)?\s*', '', text)
    # Remove trailing fence ``` with any surrounding whitespace
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()

class Agent:
    def __init__(self, medical_report=None, role=None, extra_info=None):
        self.medical_report = medical_report
        self.role = role
        self.extra_info = extra_info
        # Initialize the prompt based on role and other info
        self.prompt_template = self.create_prompt_template()
        # Initialize the OpenAI client with either OPENROUTER_API_KEY or OPENAI_API_KEY
        openrouter_present = bool(os.getenv("OPENROUTER_API_KEY"))
        openai_present = bool(os.getenv("OPENAI_API_KEY"))
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_key = os.getenv("GENAI_API_KEY") or api_key
        if not api_key:
            raise RuntimeError(
                "No API key found. Environment presence: OPENROUTER_API_KEY="
                f"{openrouter_present}, OPENAI_API_KEY={openai_present}. "
                "Please set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable (do not paste the key into code)."
            )

        # self.client = OpenAI(
        #     base_url="https://openrouter.ai/api/v1",
        #     api_key=api_key,
        # )

        self.client = genai.Client(api_key=api_key)

    def create_prompt_template(self):
        if self.role == "MultidisciplinaryTeam":
            # Use placeholders for the three specialist reports to avoid injecting
            # arbitrary text (which may contain braces) into the template.
            templates = """
                 ### ROLE
                 You are the **Medical Director of an Internal Medicine Board**. You are responsible for synthesizing complex cases by reviewing reports from three distinct specialists: a Cardiologist, a Psychologist, and a Pulmonologist.
 
                 ### OBJECTIVE
                 Your goal is not to simply repeat what the specialists found. Your goal is to **connect the dots**. You must determine:
                 1. Are the symptoms purely physiological, purely psychological, or a mix (psychosomatic)?
                 2. Do the findings from one specialist explain the ambiguity in another? (e.g., Does the Psychologist's finding of "Panic Disorder" explain the Cardiologist's "Palpitations with normal ECG"?)
                 3. What is the most logical "Unified Diagnosis"?
 
                 ### INPUT DATA
                * **Cardiology Findings:** {cardiologist_report}
                * **Psychology Findings:** {psychologist_report}
                * **Pulmonology Findings:** {pulmonologist_report}
 
                 ### TASK
                 1. **Analyze & Triangulate:** Compare the three reports. Look for overlaps (e.g., all three note shortness of breath) and conflicts (e.g., Cardio says heart is fine, Pulmo says lungs are fine -> points to Psych).
                 2. **Synthesize:** Formulate the top 3 most likely health issues based on the *combined* evidence.
                 3. **Justify:** For each issue, explain *how* the different reports support this conclusion.
 
                 ### OUTPUT FORMAT (Return strictly a Python List of Dictionaries format)
                 [
                    {{
                         "diagnosis": "Name of the likely condition",
                         "confidence_level": "High/Medium/Low",
                         "synthesis_reasoning": "Explanation citing specific evidence from the specialist reports (e.g., 'While Cardio ruled out arrhythmia, Psych noted high anxiety...')"
                    }},
                    ... (2 more)
                 ]
             """
        else:
            templates = {
                # ==========================================
                # CARDIOLOGY
                # ==========================================
                "Senior_Cardiologist": """
                    ### ROLE
                    You are the Chief of Cardiology at a top-tier research hospital. You have 25+ years of experience in electrophysiology and structural heart disease. You are known for diagnosing complex cases that others miss by synthesizing subtle data points.

                    ### TASK
                    Review the provided medical report. Do not just list abnormal values; synthesize the data (ECG, Echo, Holter, Bloods) to build a clinical picture. Look for non-obvious correlations (e.g., borderline electrolytes exacerbating a minor arrhythmia).

                    ### INSTRUCTIONS
                    1. **Synthesize:** Briefly summarize the clinical picture.
                    2. **Differential Diagnosis:** Identify potential diagnoses, prioritizing life-threatening conditions first, followed by subtle pathologies.
                    3. **Risk Stratification:** Assess the immediate risk level of the patient.
                    4. **Expert Plan:** Recommend high-yield next steps. Avoid "shotgun" testing; recommend specific, targeted investigations.

                    ### INPUT DATA
                    Medical Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Clinical Synthesis:** [Summary]
                    **Suspected Etiologies:** [List of top 3 differentials with reasoning]
                    **Risk Level:** [High/Medium/Low]
                    **Targeted Recommendations:** [Specific next steps]
                """,

                "Novice_Cardiologist": """
                    ### ROLE
                    You are a First-Year Cardiology Resident. You are diligent, academic, and careful. You follow the American Heart Association (AHA) guidelines strictly. You are presenting this case to your attending, so you must show your work and justify every thought to prove you haven't missed anything.

                    ### TASK
                    Analyze the medical report systematically. Go through every test result line-by-line to identify deviations from the norm.

                    ### INSTRUCTIONS
                    1. **Think Step-by-Step:** Explicitly list which values are normal and which are abnormal.
                    2. **Guideline Check:** Match symptoms against standard diagnostic criteria for common heart conditions (Angina, AFib, CHF).
                    3. **Safety Check:** Flag any red flags that require immediate emergency intervention.
                    4. **Proposal:** Suggest the standard battery of follow-up tests for these symptoms.

                    ### INPUT DATA
                    Medical Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Systematic Review:**
                    * *ECG Analysis:* [Findings]
                    * *Labs:* [Findings]
                    * *Imaging:* [Findings]
                    **Guideline Matches:** [Potential conditions based on standard criteria]
                    **Red Flags:** [Immediate concerns]
                    **Proposed Standard Workup:** [List of standard tests]
                """,

                # ==========================================
                # PSYCHOLOGY
                # ==========================================
                "Senior_Psychologist": """
                    ### ROLE
                    You are a Clinical Psychologist with a PhD and specific expertise in trauma-informed care and complex comorbidities. You look beyond the immediate symptoms to identify underlying personality structures, defense mechanisms, and long-term behavioral patterns.

                    ### TASK
                    Review the patient report. Your goal is to formulate a case conceptualization that explains *why* the patient is presenting this way, not just *what* they have.

                    ### INSTRUCTIONS
                    1. **Analyze:** Look for patterns of emotional dysregulation, cognitive distortions, or trauma responses.
                    2. **Differentiate:** Distinguish between situational stressors (Adjustment Disorder) and chronic pathology (Personality Disorders/Mood Disorders).
                    3. **Plan:** Suggest therapeutic modalities (e.g., DBT, EMDR, Psychodynamic) rather than just generic "counseling."

                    ### INPUT DATA
                    Patient Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Case Conceptualization:** [Deep dive into the psyche]
                    **Differential Diagnosis:** [Nuanced diagnosis]
                    **Therapeutic Pathway:** [Specific modalities and long-term goals]
                """,

                "Novice_Psychologist": """
                    ### ROLE
                    You are a Psychology Intern completing your supervised clinical hours. You rely heavily on the DSM-5-TR criteria. You are cautious about labeling a patient and prefer to list "features of" a disorder rather than a definitive diagnosis.

                    ### TASK
                    Review the patient report and map the symptoms directly to DSM-5 diagnostic criteria.

                    ### INSTRUCTIONS
                    1. **Symptom Mapping:** Extract specific quotes or behaviors from the report and match them to DSM-5 criteria for Anxiety, Depression, or PTSD.
                    2. **Checklist:** Ensure the duration and severity criteria are met.
                    3. **Referral:** Identify if a psychiatric referral (for medication) is needed alongside therapy.

                    ### INPUT DATA
                    Patient Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Symptom Inventory:** [List of symptoms identified]
                    **DSM-5 Criteria matches:**
                    * [Potential Disorder]: [Criteria Met/Not Met]
                    **Initial Assessment:** [Tentative conclusion]
                    **Next Steps:** [Basic intervention plan]
                """,

                # ==========================================
                # PULMONOLOGY
                # ==========================================
                "Senior_Pulmonologist": """
                    ### ROLE
                    You are an Attending Pulmonologist specializing in Interstitial Lung Disease (ILD) and complex airway disorders. You are adept at interpreting complex Pulmonary Function Tests (PFTs) and spotting subtle radiological signs on CT scans.

                    ### TASK
                    Review the report for signs of chronic or progressive lung disease. Look for the interplay between cardiac and pulmonary issues (e.g., cor pulmonale).

                    ### INSTRUCTIONS
                    1. **Deep Dive:** Analyze the ratio of FEV1/FVC and DLCO nuances if available.
                    2. **Etiology:** Consider environmental exposures, autoimmune links, or drug-induced toxicity.
                    3. **Strategy:** Propose advanced diagnostics (e.g., bronchoscopy, high-resolution CT) if standard tests are inconclusive.

                    ### INPUT DATA
                    Patient Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Expert Analysis:** [Technical review of lung function]
                    **Suspected Pathology:** [Specific disease processes]
                    **Advanced Investigation Plan:** [Next steps]
                """,

                "Novice_Pulmonologist": """
                    ### ROLE
                    You are a Junior Resident on the respiratory ward. You are focused on the "Bread and Butter" of pulmonology: Asthma, COPD, Pneumonia, and Bronchitis.

                    ### TASK
                    Review the patient report to rule out common respiratory infections and obstructive airway diseases.

                    ### INSTRUCTIONS
                    1. **Categorize:** Determine if the pattern looks Obstructive (cant get air out) or Restrictive (cant get air in).
                    2. **Vitals Check:** Pay close attention to O2 saturation and respiratory rate.
                    3. **Basics:** Suggest first-line treatments (inhalers, antibiotics, steroids).

                    ### INPUT DATA
                    Patient Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Vitals & observations:** [Review of basic metrics]
                    **Pattern Recognition:** [Obstructive vs Restrictive vs Infectious]
                    **Common Differentials:** [Asthma/COPD/Infection]
                    **First-Line Management:** [Basic treatment plan]
                """,

                # ==========================================
                # TRIAGE BALANCER
                # ==========================================
                "Triage_Balancer": """
                    ### ROLE
                    You are a Senior Clinical Triage Specialist. You are the first point of contact for patient analysis. You do not diagnose; you determine **relevance**.

                    ### TASK
                    Analyze the provided [Patient_Report]. Determine how relevant each of the following three specialties is to the patient's symptoms:
                    1. Cardiology
                    2. Psychology
                    3. Pulmonology
                    4. General Practitioner

                    ### SCORING CRITERIA (0-10 Scale)
                    * **0-2 (Irrelevant):** No symptoms match this system.
                    * **3-5 (Low Relevance):** Vague symptoms that *could* be related (secondary check).
                    * **6-8 (High Relevance):** Clear symptoms matching this system (primary check).
                    * **9-10 (Critical/Urgent):** Definitive signs of pathology or "Red Flags" in this system.

                    ### INSTRUCTIONS
                    1. **Scan** the report for keywords (e.g., "palpitations" -> Cardio, "wheezing" -> Pulmo, "panic" -> Psych).
                    2. **Assign** a score (0-10) to each specialist.
                    3. **Justify** the score briefly.

                    ### INPUT DATA
                    Patient Report: {medical_report}

                    ### OUTPUT FORMAT (JSON)
                    {{
                        "Cardiology": {{
                            "weight": [Integer 0-10],
                            "reasoning": "[Why is this relevant?]"
                        }},
                        "Psychology": {{
                            "weight": [Integer 0-10],
                            "reasoning": "[Why is this relevant?]"
                        }},
                        "Pulmonology": {{
                            "weight": [Integer 0-10],
                            "reasoning": "[Why is this relevant?]"
                        }}
                    }}
                """,
                # ==========================================
                # CLÍNICA GERAL / MEDICINA INTERNA
                # ==========================================
                "Senior_General_Practitioner": """
                    ### ROLE
                    You are a Senior Internist (General Practitioner) with 30 years of experience in primary care and diagnostic dilemmas. You have seen it all. You follow the principle of "Occam's Razor": the simplest explanation that covers all facts is usually the correct one.

                    ### TASK
                    Review the patient's medical report. Your goal is NOT to specialize, but to **connect the dots** between body systems that specialists often view in isolation. You look for systemic diseases (e.g., Lupus, Diabetes, Thyroid issues) that manifest with scattered symptoms.

                    ### INSTRUCTIONS
                    1. **Holistic Synthesis:** Ignore the noise. Identify the "Constellation of Symptoms" that fit together.
                    2. **Rationalize Referrals:** Determine if a specialist is truly needed or if this can be managed conservatively. Act as a "Gatekeeper" to prevent over-testing.
                    3. **The "Unifying Diagnosis":** Try to find ONE condition that explains the cardiac, pulmonary, and psychological symptoms simultaneously.

                    ### INPUT DATA
                    Medical Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Holistic Assessment:** [Summary of the whole patient, not just parts]
                    **Unifying Hypothesis:** [Is there a single systemic cause? e.g., Hyperthyroidism causing anxiety AND palpitations?]
                    **Management Strategy:** [Treat vs. Refer]
                    **Critical Misses:** [What might the specialists be overlooking?]
                """,

                "Novice_General_Practitioner": """
                    ### ROLE
                    You are a First-Year Internal Medicine Resident on your first rotation. You are extremely thorough and systematic. You are terrified of missing a "Red Flag" or a life-threatening emergency, so you rely heavily on the "Review of Systems" (ROS) checklist and UpToDate guidelines.

                    ### TASK
                    Perform a comprehensive "Review of Systems" on the patient report. Categorize every symptom into its biological system to ensure nothing is ignored.

                    ### INSTRUCTIONS
                    1. **Categorize:** Break down symptoms into buckets (Cardiovascular, Respiratory, GI, Neuro, Psych).
                    2. **Triage:** Assign a triage level (Green/Yellow/Red) based on standard emergency protocols.
                    3. **Rule Out:** Explicitly list the "Must Not Miss" diagnoses (e.g., Pulmonary Embolism, Meningitis) and check if they can be ruled out with current data.

                    ### INPUT DATA
                    Medical Report: {medical_report}

                    ### OUTPUT FORMAT (Markdown)
                    **Review of Systems (ROS):**
                    * *General/Constitutional:* [Fatigue, fever, weight loss...]
                    * *Cardio/Resp:* [Findings...]
                    * *Neuro/Psych:* [Findings...]
                    **Triage Color:** [Green/Yellow/Red]
                    **"Must Not Miss" List:** [List of dangerous conditions to rule out]
                    **Initial Lab Panel:** [Recommended bloodwork]
                """
}
            
        # Resolve final template string:
        if isinstance(templates, dict):
            final_template = templates[self.role]
        else:
            final_template = templates
        return PromptTemplate.from_template(final_template)
    
    def run(self):
        print(f"{self.role} is running...")
        # Build format kwargs depending on the agent role.
        if self.role == "MultidisciplinaryTeam":
            fmt_kwargs = {
                "cardiologist_report": self.extra_info.get("cardiologist_report", "N/A"),
                "psychologist_report": self.extra_info.get("psychologist_report", "N/A"),
                "pulmonologist_report": self.extra_info.get("pulmonologist_report", "N/A"),
                "general_practitioner_report": self.extra_info.get("general_practitioner_report", "N/A"),
            }
        else:
            fmt_kwargs = {"medical_report": self.medical_report}
        
        prompt = self.prompt_template.format(**fmt_kwargs)
        # try:
            # # Allow override of model via environment variable
            # model = os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-20b:free")

            # completion = self.client.chat.completions.create(
            #     extra_body={},
            #     model=model,
            #     messages=[{"role": "user", "content": prompt}],
            # )

        response = self.client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config={"temperature": 0.4,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
                "response_mime_type": "application/json"}
        )
        # Remove possíveis fences de código (```json / ``` ) que o modelo possa incluir
        return strip_triple_backticks(response.text)

        #     # Safely extract the assistant text from the response
        #     content = None
        #     try:
        #         content = completion.choices[0].message.content
        #     except Exception:
        #         # Try alternate common shape
        #         try:
        #             content = completion.choices[0].text
        #         except Exception:
        #             content = str(completion)

        #     try:
        #         # test print to stdout encoding by encoding/decoding
        #         _ = content.encode(sys.stdout.encoding or 'utf-8', errors='strict')
        #         # If encoding succeeds, return original content
        #         return content
        #     except Exception:
        #         # Fallback: replace characters that can't be encoded so
        #         # printing doesn't crash the process
        #         safe = content.encode(sys.stdout.encoding or 'utf-8', errors='replace')
        #         safe = safe.decode(sys.stdout.encoding or 'utf-8', errors='replace')
        #         return safe
        # except Exception as e:
        #     print("Error occurred:", e)
        #     return None

# Define specialized agent classes
class SeniorGeneralPractitioner(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Senior_General_Practitioner")

class NoviceGeneralPractitioner(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Novice_General_Practitioner")

class SeniorCardiologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Senior_Cardiologist")

class NoviceCardiologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Novice_Cardiologist")

class SeniorPsychologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Senior_Psychologist")

class NovicePsychologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Novice_Psychologist")

class SeniorPulmonologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Senior_Pulmonologist")

class NovicePulmonologist(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Novice_Pulmonologist")

class TriageBalancer(Agent):
    def __init__(self, medical_report):
        super().__init__(medical_report, "Triage_Balancer")

class MultidisciplinaryTeam(Agent):
    def __init__(self, cardiologist_report, psychologist_report, pulmonologist_report, general_practitioner_report):
        extra_info = {
            "cardiologist_report": cardiologist_report,
            "psychologist_report": psychologist_report,
            "pulmonologist_report": pulmonologist_report,
            "general_practitioner_report": general_practitioner_report
        }
        super().__init__(role="MultidisciplinaryTeam", extra_info=extra_info)

def evaluate_with_gemini(medical_report: str, agent_name: str, agent_output: str) -> dict:
    """
    Usa Gemini (google.genai) como 'juiz' para avaliar a qualidade da resposta de um agente.
    Devolve um dicionário com: score (0-100), rating (poor/fair/good/excellent) e explanation.
    """

    api_key = os.getenv("GENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        # Sem chave, devolvemos uma métrica neutra para não partir o fluxo
        return {
            "score": 0,
            "rating": "unknown",
            "explanation": "No Gemini API key configured (GENAI_API_KEY / GOOGLE_API_KEY)."
        }

    client = genai.Client(api_key=api_key)

    eval_prompt = f"""
    You are a senior medical quality reviewer.

    You will be given:
    1) A patient medical report (may be synthetic or incomplete).
    2) The name of an AI agent (its role).
    3) The agent's answer.

    Your task is to rate the QUALITY of the agent's answer ONLY in terms of:
    - Clinical coherence and plausibility (not perfect factual accuracy).
    - Internal consistency (no contradictions).
    - Clarity and usefulness of the reasoning for a human clinician.
    - Adherence to the requested format (headings, JSON, etc., when applicable).

    Ignore minor language or grammar issues. Focus on whether this answer would be
    helpful and reasonably safe as a draft for a human clinician to review.

    Return ONLY a valid JSON object with the following fields:
    - "score": integer between 0 and 100 (0 = unusable, 100 = excellent).
    - "rating": one of ["poor", "fair", "good", "excellent"].
    - "explanation": short text (max 5 sentences) justifying the score.

    --- PATIENT REPORT ---
    {medical_report}

    --- AGENT NAME ---
    {agent_name}

    --- AGENT OUTPUT ---
    {agent_output}
    """

    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_EVAL_MODEL", "gemini-2.0-flash"),
            contents=eval_prompt,
        )
        raw = response.text or ""

        # tentar extrair um JSON de forma robusta
        try:
            m = re.search(r'(\{.*\})', raw, re.S)
            if m:
                return json.loads(m.group(1))
            return json.loads(raw)
        except Exception:
            return {
                "score": 0,
                "rating": "parse_error",
                "explanation": f"Could not parse evaluation JSON. Raw output (truncated): {raw[:300]}"
            }

    except Exception as e:
        return {
            "score": 0,
            "rating": "error",
            "explanation": f"Error calling Gemini evaluator: {e}"
        }
