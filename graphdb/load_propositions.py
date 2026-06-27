import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

from config import paths
load_dotenv(paths.ENV)

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
)

propositions = [
    {
        "id": "P01",
        "allegation_para": "Para 6",
        "text": "It was an express term of the MSA and SOW that the go-live date was fixed at 1 October 2024 and that time was of the essence in respect of that date.",
        "legal_element": "contract_terms",
        "importance_weight": 3,
        "expected_status": "contradicted",
        "note": "SOW clause 2.1 says target date. MSA clause 3.1 says reasonable endeavours. Neither fixes the date or makes time of the essence. Change Order 3 also revised the date to 18 Nov with Meridian's agreement.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P02",
        "allegation_para": "Para 7",
        "text": "At a meeting on or about 5 February 2024, TechFlow's Sales Director Daniel Frost orally represented to Meridian that the platform would reliably support at least 10,000 concurrent transactions, and Meridian entered into the MSA in reliance on that representation.",
        "legal_element": "misrepresentation",
        "importance_weight": 2,
        "expected_status": "gap",
        "note": "No document in the bundle references this meeting, Daniel Frost, or the 10,000 transaction figure. MSA clause 22 entire agreement clause expressly excludes liability for pre-contractual representations not in the contract save fraud.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P03",
        "allegation_para": "Para 8",
        "text": "TechFlow delivered the platform late — the platform did not go live until 18 November 2024, seven weeks after the contractual go-live date of 1 October 2024.",
        "legal_element": "delay",
        "importance_weight": 3,
        "expected_status": "weakly_supported",
        "note": "Platform did go live on 18 November not 1 October. However Change Order 3 signed by Meridian revised the go-live date to 18 November 2024 making that the contractually agreed date. This allegation depends entirely on P01 succeeding.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P04",
        "allegation_para": "Para 9",
        "text": "Meridian did not at any time request any change to the agreed scope of works. All delay was caused by TechFlow's failure to allocate adequate and competent resources.",
        "legal_element": "scope_change",
        "importance_weight": 3,
        "expected_status": "contradicted",
        "note": "Directly contradicted by Change Order 3 signed by Priya Nair on 2 Sep 2024 adding the loyalty module at Meridian's request. Also contradicted by Tab 10 email, Vance WS para 3, and Nair WS para 3. One of the clearest self-contradictions in the bundle.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P05",
        "allegation_para": "Para 10",
        "text": "On numerous occasions prior to go-live, Meridian warned TechFlow that the platform was not ready and requested that go-live be deferred. TechFlow ignored those warnings and proceeded to go-live on 18 November 2024.",
        "legal_element": "go_live_decision",
        "importance_weight": 2,
        "expected_status": "contradicted",
        "note": "Directly inverted by Tab 9 email. TechFlow recommended deferral to January 2025 in writing on 24 October 2024. Meridian rejected that advice and instructed TechFlow to proceed saying she was content to take that risk on Meridian's side. Vance WS para 4 admits this.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P06",
        "allegation_para": "Para 11",
        "text": "Following go-live, the platform was unavailable for more than 40% of trading hours during November and December 2024, causing widespread till failures and inability to process sales across Meridian's store estate.",
        "legal_element": "platform_availability",
        "importance_weight": 3,
        "expected_status": "contradicted",
        "note": "Directly contradicted by Meridian's own IT expert Whitfield paras 2-4: platform unavailability attributable to the platform was approximately 6.2% of trading hours. He found no support in the logs for the 40% figure. The 25 Nov outage was Northgate Telecom network failure not the platform. Defect log corroborates.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P07",
        "allegation_para": "Para 12",
        "text": "The platform contained numerous defects including critical Severity 1 failures in the stock-synchronisation module which caused stores to display and sell against incorrect stock figures. The platform was not of satisfactory quality and not fit for purpose.",
        "legal_element": "platform_defects",
        "importance_weight": 3,
        "expected_status": "supported",
        "note": "Well supported. Whitfield confirms D-001 and D-002 were genuine Severity 1 defects falling below the standard of a competent supplier paras 5-6. Defect log documents both. Vance WS para 5 corroborates. Okafor WS para 2 corroborates. This is Meridian's strongest allegation.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P08",
        "allegation_para": "Para 13",
        "text": "Meridian did not accept the platform or any part of it, and no acceptance or sign-off was given by Meridian at any time.",
        "legal_element": "acceptance",
        "importance_weight": 3,
        "expected_status": "contradicted",
        "note": "Directly contradicted by the UAT Acceptance Certificate Tab 8 signed by Priya Nair on 12 November 2024 stating Phase 1 has passed User Acceptance Testing and is accepted with no outstanding Severity 1 or 2 items. Nair WS para 4 confirms she signed it.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P09",
        "allegation_para": "Para 14",
        "text": "TechFlow failed to provide adequate training to Meridian's staff in the use of the platform.",
        "legal_element": "training",
        "importance_weight": 1,
        "expected_status": "gap",
        "note": "SOW clause 3.2 explicitly states training of Meridian's staff is the Customer's responsibility. TechFlow's obligation was a train-the-trainer session and written guides only. No evidence in the bundle that even this was not provided. This allegation faces both an evidential gap and a contractual bar.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P10",
        "allegation_para": "Para 15(a)",
        "text": "Meridian suffered wasted expenditure of £1,800,000 being sums paid to TechFlow under the MSA.",
        "legal_element": "loss_wasted_expenditure",
        "importance_weight": 2,
        "expected_status": "supported",
        "note": "Supported. Greenhalgh FCA para 2 confirms £1.8m is consistent with accounting records. Nair WS para 5 confirms £1.8m was paid. MSA clause 14.2 caps liability at charges paid in preceding 12 months. TechFlow counterclaims £600,000 in unpaid milestones which would reduce net recovery.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P11",
        "allegation_para": "Para 15(b)",
        "text": "Meridian suffered loss of profit of £4,200,000 during the peak trading period of November and December 2024 by reason of the platform failures.",
        "legal_element": "loss_of_profit",
        "importance_weight": 3,
        "expected_status": "contradicted",
        "note": "Substantially contradicted by Meridian's own forensic accountant Greenhalgh paras 3-5: supportable figure is approximately £1.3m not £4.2m. Approximately £1.5m of the shortfall is attributable to the Lutterworth DC flood and sector-wide retail downturn evidenced by Okafor internal email Tab 12 and Okafor WS para 4. MSA clause 14.1 excludes liability for loss of profit entirely.",
        "status": "pending",
        "risk_score": 0.0
    },
    {
        "id": "P12",
        "allegation_para": "MSA clause 14",
        "text": "TechFlow's liability for loss of profit is excluded under MSA clause 14.1, and total liability is capped at charges actually paid under MSA clause 14.2.",
        "legal_element": "contractual_limitation",
        "importance_weight": 3,
        "expected_status": "supported",
        "note": "This is TechFlow's defence point not Meridian's allegation. Included because it is the most important legal issue in the case. If clause 14 is effective the £4.2m loss of profit claim is entirely excluded and total recovery is capped at approximately £1.8m. Greenhalgh flags this at para 6. TechFlow response letter Tab 15 relies on it.",
        "status": "pending",
        "risk_score": 0.0
    },
]

with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
    for prop in propositions:
        session.run("""
            MERGE (p:Proposition {id: $id})
            SET p.allegation_para = $allegation_para,
                p.text = $text,
                p.legal_element = $legal_element,
                p.importance_weight = $importance_weight,
                p.expected_status = $expected_status,
                p.note = $note,
                p.status = $status,
                p.risk_score = $risk_score
        """, **prop)
        print(f"Loaded: {prop['id']} — {prop['text'][:60]}...")

driver.close()
print(f"\nAll {len(propositions)} propositions loaded successfully.")
