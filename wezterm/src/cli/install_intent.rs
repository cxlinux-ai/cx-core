/*
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
*/
//! Natural language install intent matching for demo-safe offline operation.

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InstallPlanStatus {
    Ready,
    NeedsClarification,
    Unknown,
}

#[derive(Debug, Clone)]
pub struct InstallPlan {
    pub status: InstallPlanStatus,
    pub topic: String,
    pub packages: Vec<String>,
    pub alternatives: Vec<String>,
    pub reasoning: String,
    pub confidence: f32,
}

impl InstallPlan {
    pub fn apt_command(&self, auto_confirm: bool) -> Option<String> {
        if self.status != InstallPlanStatus::Ready || self.packages.is_empty() {
            return None;
        }

        let yes_flag = if auto_confirm { " -y" } else { "" };
        Some(format!(
            "sudo apt install{} {}",
            yes_flag,
            self.packages.join(" ")
        ))
    }

    pub fn summary_lines(&self) -> Vec<String> {
        let mut lines = vec![
            format!("I understood you want to {}.", self.topic),
            format!("Reasoning: {}", self.reasoning),
            format!("Confidence: {:.0}%", self.confidence * 100.0),
        ];

        if !self.packages.is_empty() {
            lines.push(format!("Packages: {}", self.packages.join(", ")));
        }

        if !self.alternatives.is_empty() {
            lines.push(format!("Alternatives: {}", self.alternatives.join(", ")));
        }

        lines
    }
}

struct Candidate {
    topic: &'static str,
    packages: &'static [&'static str],
    alternatives: &'static [&'static str],
    reasoning: &'static str,
    confidence: f32,
}

pub fn resolve_install_intent(query: &str) -> InstallPlan {
    let tokens = tokenize(query);
    let normalized = tokens.join(" ");

    if tokens.is_empty() {
        return clarification_plan("install software", "No package or goal was provided.", 0.2);
    }

    if is_ambiguous_request(&tokens) {
        return clarification_plan(
            "install software",
            "The request names a broad goal but not enough detail to choose packages safely.",
            0.42,
        );
    }

    let mut candidates = Vec::new();

    if let Some(candidate) = docker_kubernetes_candidate(&tokens, &normalized) {
        candidates.push(candidate);
    }
    if let Some(candidate) = machine_learning_candidate(&tokens, &normalized) {
        candidates.push(candidate);
    }
    if let Some(candidate) = python_dev_candidate(&tokens, &normalized) {
        candidates.push(candidate);
    }
    if let Some(candidate) = web_server_candidate(&tokens, &normalized) {
        candidates.push(candidate);
    }
    if let Some(candidate) = docker_candidate(&tokens) {
        candidates.push(candidate);
    }

    if let Some(best) = candidates
        .into_iter()
        .max_by(|left, right| left.confidence.total_cmp(&right.confidence))
    {
        // Keep the ready threshold high enough that demo-safe package installs
        // only run for direct profile matches or clear fuzzy matches.
        if best.confidence >= 0.68 {
            return InstallPlan {
                status: InstallPlanStatus::Ready,
                topic: best.topic.to_string(),
                packages: best.packages.iter().map(|pkg| pkg.to_string()).collect(),
                alternatives: best
                    .alternatives
                    .iter()
                    .map(|alt| alt.to_string())
                    .collect(),
                reasoning: best.reasoning.to_string(),
                confidence: best.confidence,
            };
        }

        return InstallPlan {
            status: InstallPlanStatus::NeedsClarification,
            topic: best.topic.to_string(),
            packages: Vec::new(),
            alternatives: best
                .alternatives
                .iter()
                .map(|alt| alt.to_string())
                .collect(),
            reasoning: format!(
                "{} I need more detail before choosing packages safely.",
                best.reasoning
            ),
            confidence: best.confidence,
        };
    }

    InstallPlan {
        status: InstallPlanStatus::Unknown,
        topic: "install software".to_string(),
        packages: Vec::new(),
        alternatives: vec![
            "machine learning tools".to_string(),
            "web server".to_string(),
            "python development environment".to_string(),
            "docker and kubernetes".to_string(),
        ],
        reasoning: "I could not map the request to a known install profile or safe package set."
            .to_string(),
        confidence: 0.18,
    }
}

fn machine_learning_candidate(tokens: &[String], normalized: &str) -> Option<Candidate> {
    let mut confidence: f32 = 0.0;

    if normalized.contains("machine learning") {
        confidence = confidence.max(0.94);
    }
    if normalized.contains("data science") {
        confidence = confidence.max(0.9);
    }
    if has_token(tokens, "ml") || has_token(tokens, "ai") {
        confidence = confidence.max(0.74);
    }
    if has_all(tokens, &["python"]) && has_any(tokens, &["numpy", "pandas", "scipy", "sklearn"]) {
        confidence = confidence.max(0.86);
    }
    if has_any(tokens, &["tensorflow", "pytorch", "torch"]) {
        confidence = confidence.max(0.8);
    }

    (confidence > 0.0).then_some(Candidate {
        topic: "install a machine learning Python toolkit",
        packages: &[
            "python3",
            "python3-pip",
            "python3-venv",
            "python3-numpy",
            "python3-scipy",
            "python3-pandas",
            "python3-sklearn",
        ],
        alternatives: &[
            "Use pip inside a virtual environment for TensorFlow or PyTorch",
            "Install Jupyter with pip if notebooks are needed",
        ],
        reasoning: "The request mentions machine learning or data science, so I selected the common Python scientific stack available from apt.",
        confidence,
    })
}

fn python_dev_candidate(tokens: &[String], normalized: &str) -> Option<Candidate> {
    let mut confidence: f32 = 0.0;

    if normalized.contains("python development") || normalized.contains("python dev") {
        confidence = confidence.max(0.96);
    }
    if has_all(tokens, &["python"])
        && has_any(
            tokens,
            &["development", "dev", "environment", "env", "setup"],
        )
    {
        confidence = confidence.max(0.9);
    }
    if has_all(tokens, &["pyton"]) && has_any(tokens, &["dev", "env"]) {
        confidence = confidence.max(0.82);
    }

    (confidence > 0.0).then_some(Candidate {
        topic: "set up a Python development environment",
        packages: &[
            "python3",
            "python3-pip",
            "python3-venv",
            "python3-dev",
            "build-essential",
        ],
        alternatives: &[
            "Add python3-poetry for Poetry projects",
            "Add pipx for isolated Python command-line tools",
        ],
        reasoning: "The request names Python plus a development environment, so I selected the interpreter, pip, venv, headers, and build tools.",
        confidence,
    })
}

fn web_server_candidate(tokens: &[String], normalized: &str) -> Option<Candidate> {
    let mut confidence: f32 = 0.0;

    if normalized.contains("web server") || normalized.contains("http server") {
        confidence = confidence.max(0.82);
    }
    if has_any(tokens, &["nginx", "ngnix"]) {
        confidence = confidence.max(0.95);
    }
    if has_all(tokens, &["web", "server"]) {
        confidence = confidence.max(0.8);
    }

    (confidence > 0.0).then_some(Candidate {
        topic: "install a web server",
        packages: &["nginx"],
        alternatives: &["apache2", "caddy", "lighttpd"],
        reasoning: "The request asks for a web or HTTP server. I selected nginx as the default lightweight web server and listed common alternatives.",
        confidence,
    })
}

fn docker_kubernetes_candidate(tokens: &[String], _normalized: &str) -> Option<Candidate> {
    if has_any(tokens, &["docker", "dockr"])
        && has_any(tokens, &["kubernetes", "kubernets", "kubectl", "k8s"])
    {
        return Some(Candidate {
            topic: "install Docker and Kubernetes command-line tooling",
            packages: &["docker.io", "kubernetes-client"],
            alternatives: &[
                "Use the upstream Docker repository for the newest Docker Engine",
                "Use kind or minikube for a local Kubernetes cluster",
            ],
            reasoning: "The request mentions Docker and Kubernetes, so I selected the distro Docker package plus the apt package that provides kubectl.",
            confidence: 0.94,
        });
    }

    None
}

fn docker_candidate(tokens: &[String]) -> Option<Candidate> {
    if has_any(tokens, &["docker", "dockr"]) {
        return Some(Candidate {
            topic: "install Docker",
            packages: &["docker.io"],
            alternatives: &["podman", "containerd"],
            reasoning: "The request mentions Docker, so I selected the distro Docker package and listed compatible container alternatives.",
            confidence: 0.88,
        });
    }

    None
}

fn clarification_plan(topic: &str, reasoning: &str, confidence: f32) -> InstallPlan {
    InstallPlan {
        status: InstallPlanStatus::NeedsClarification,
        topic: topic.to_string(),
        packages: Vec::new(),
        alternatives: vec![
            "machine learning tools".to_string(),
            "web server".to_string(),
            "python development environment".to_string(),
            "docker and kubernetes".to_string(),
        ],
        reasoning: reasoning.to_string(),
        confidence,
    }
}

fn is_ambiguous_request(tokens: &[String]) -> bool {
    let meaningful: Vec<&String> = tokens.iter().filter(|token| !is_stopword(token)).collect();

    if meaningful.is_empty() {
        return true;
    }

    if meaningful.len() == 1
        && matches!(
            meaningful[0].as_str(),
            "something" | "stuff" | "tools" | "software"
        )
    {
        return true;
    }

    has_any(tokens, &["server"])
        && !has_any(
            tokens,
            &["web", "http", "nginx", "apache", "database", "ssh"],
        )
}

fn tokenize(query: &str) -> Vec<String> {
    query
        .to_lowercase()
        .split(|ch: char| !ch.is_ascii_alphanumeric() && ch != '-' && ch != '_')
        .filter(|word| !word.is_empty())
        .map(|word| word.to_string())
        .collect()
}

fn has_all(tokens: &[String], needles: &[&str]) -> bool {
    needles.iter().all(|needle| has_token(tokens, needle))
}

fn has_any(tokens: &[String], needles: &[&str]) -> bool {
    needles.iter().any(|needle| has_token(tokens, needle))
}

fn has_token(tokens: &[String], needle: &str) -> bool {
    tokens.iter().any(|token| token_matches(token, needle))
}

fn token_matches(token: &str, needle: &str) -> bool {
    if token == needle {
        return true;
    }

    if token.len() <= 2 || needle.len() <= 2 {
        return false;
    }

    let distance = levenshtein(token, needle);
    let limit = if needle.len() <= 5 { 1 } else { 2 };
    distance <= limit
}

fn levenshtein(left: &str, right: &str) -> usize {
    let mut costs: Vec<usize> = (0..=right.len()).collect();

    for (i, left_char) in left.chars().enumerate() {
        let mut previous = i;
        costs[0] = i + 1;

        for (j, right_char) in right.chars().enumerate() {
            let insert = costs[j + 1] + 1;
            let delete = costs[j] + 1;
            let replace = previous + usize::from(left_char != right_char);
            previous = costs[j + 1];
            costs[j + 1] = insert.min(delete).min(replace);
        }
    }

    costs[right.len()]
}

fn is_stopword(token: &str) -> bool {
    matches!(
        token,
        "a" | "an"
            | "and"
            | "for"
            | "i"
            | "install"
            | "instal"
            | "need"
            | "please"
            | "set"
            | "setup"
            | "the"
            | "to"
            | "up"
            | "want"
            | "with"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_ready(query: &str, expected_package: &str) -> InstallPlan {
        let plan = resolve_install_intent(query);
        assert_eq!(
            plan.status,
            InstallPlanStatus::Ready,
            "{}: {:?}",
            query,
            plan
        );
        assert!(
            plan.packages
                .iter()
                .any(|package| package == expected_package),
            "{}: expected package {}, got {:?}",
            query,
            expected_package,
            plan.packages
        );
        assert!(plan.confidence >= 0.68, "{}: {:?}", query, plan);
        plan
    }

    #[test]
    fn handles_required_natural_language_install_cases() {
        assert_ready("install something for machine learning", "python3-sklearn");
        assert_ready("I need a web server", "nginx");
        assert_ready("set up python development environment", "python3-venv");
        assert_ready("install docker and kubernetes", "kubernetes-client");
    }

    #[test]
    fn handles_typos_in_demo_requests() {
        assert_ready("instal dockr and kubernets", "docker.io");
        assert_ready("install pyton dev env", "python3-pip");
        assert_ready("install ngnix web serber", "nginx");
    }

    #[test]
    fn handles_additional_natural_language_cases() {
        assert_ready("give me a data science toolkit", "python3-pandas");
        assert_ready("please install docker", "docker.io");
        assert_ready("I want an http server", "nginx");
    }

    #[test]
    fn handles_ambiguous_requests_gracefully() {
        let plan = resolve_install_intent("install something");
        assert_eq!(plan.status, InstallPlanStatus::NeedsClarification);
        assert!(plan.packages.is_empty());
        assert!(!plan.alternatives.is_empty());

        let server_plan = resolve_install_intent("I need a server");
        assert_eq!(server_plan.status, InstallPlanStatus::NeedsClarification);
        assert!(server_plan.reasoning.contains("not enough detail"));
    }

    #[test]
    fn handles_unknown_requests_gracefully() {
        let plan = resolve_install_intent("install obscure thingamabob");
        assert_eq!(plan.status, InstallPlanStatus::Unknown);
        assert!(plan.packages.is_empty());
        assert!(!plan.alternatives.is_empty());
    }

    #[test]
    fn exposes_reasoning_confidence_and_command() {
        let plan = resolve_install_intent("install docker and kubernetes");
        let lines = plan.summary_lines().join("\n");

        assert!(lines.contains("I understood you want"));
        assert!(lines.contains("Reasoning:"));
        assert!(lines.contains("Confidence:"));
        assert_eq!(
            plan.apt_command(false),
            Some("sudo apt install docker.io kubernetes-client".to_string())
        );
        assert_eq!(
            plan.apt_command(true),
            Some("sudo apt install -y docker.io kubernetes-client".to_string())
        );
    }
}
