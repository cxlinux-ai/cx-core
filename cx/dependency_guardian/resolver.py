"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1

ConflictResolver - AI-powered resolution strategy generator for dependency conflicts.
"""

from typing import Dict, List, Any
from .guardian import ConflictReport

class ConflictResolver:
    """
    Generates human-readable and machine-executable resolution strategies
    for identified package conflicts.
    
    Provides confidence-ranked suggestions based on heuristic graph analysis.
    """
    def resolve(self, report: ConflictReport) -> Dict[str, Any]:
        """
        Analyzes a ConflictReport and returns ranked AI suggestions.
        """
        suggestions = []
        
        for conflict in report.predicted_conflicts:
            conflict_type = conflict.get("type", "UNKNOWN")
            
            if conflict_type == "VIRTUAL_CONFLICT":
                provider = conflict.get("provider", "unknown")
                virtual = conflict.get("virtual", "capability")
                suggestions.append({
                    "action": f"REPLACE {provider} WITH {report.target}",
                    "confidence": 0.85,
                    "risk": "MEDIUM",
                    "rationale": f"Both packages provide the '{virtual}' capability. Transitioning is standard but requires backup."
                })
            elif conflict_type == "DIRECT_CONFLICT":
                suggestions.append({
                    "action": f"ABORT {report.target} INSTALLATION",
                    "confidence": 0.95,
                    "risk": "CRITICAL",  # Corrected from LOW to match rationale
                    "rationale": "A hard conflict was detected. Installing would break system integrity."
                })
            elif conflict_type == "REVERSE_CONFLICT":
                aggressor = conflict.get("aggressor", "installed package")
                suggestions.append({
                    "action": f"REMOVE {aggressor} BEFORE INSTALLING {report.target}",
                    "confidence": 0.75,
                    "risk": "HIGH",
                    "rationale": f"Existing package '{aggressor}' explicitly blocks this installation path."
                })
            else:
                # Handle unknown/unrecognized conflict types
                suggestions.append({
                    "action": "MANUAL REVIEW REQUIRED",
                    "confidence": 0.20,
                    "risk": "HIGH",
                    "rationale": f"Unhandled conflict type '{conflict_type}' detected. System state may be inconsistent."
                })

        # Rank suggestions by confidence (highest first)
        suggestions.sort(key=lambda s: s["confidence"], reverse=True)

        # Nuanced safety score calculation
        # 1.0 = SAFE
        # 0.0 = UNKNOWN_STATE (hard failure)
        # 0.1-0.5 = CONFLICT_DETECTED (based on risk)
        
        if report.status == "SAFE":
            safety_score = 1.0
        elif report.status == "UNKNOWN_STATE":
            safety_score = 0.0
        else:
            # Derive score from highest risk
            risks = [s["risk"] for s in suggestions]
            if "CRITICAL" in risks:
                safety_score = 0.1
            elif "HIGH" in risks:
                safety_score = 0.3
            else:
                safety_score = 0.5

        return {
            "target": report.target,
            "suggestions": suggestions,
            "overall_safety_score": safety_score,
            "status": report.status
        }
