/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! HRM AI Agent Hiring Command
//!
//! Deploys AI agents to managed servers with enterprise-grade compliance.
//! This module is only available when the `hrm` feature is enabled.
//!
//! # Example
//! ```bash
//! # Deploy a DevOps agent
//! cx hire devops --server prod-1 --name "Deploy Bot"
//!
//! # Deploy with custom configuration
//! cx hire security --server sec-cluster --capabilities audit,scan,patch
//! ```

use anyhow::Result;
use clap::Parser;

#[cfg(feature = "hrm")]
use hrm_ai::{
    agent::AgentStatus,
    hire::{AgentHiringService, HireConfig},
    theme::SovereignTheme,
};

/// Agent types available for deployment
#[derive(Debug, Clone, Copy, clap::ValueEnum)]
pub enum AgentType {
    /// DevOps automation agent
    Devops,
    /// Security monitoring agent
    Security,
    /// Database administration agent
    Database,
    /// Network management agent
    Network,
    /// Support and helpdesk agent
    Support,
}

impl std::fmt::Display for AgentType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AgentType::Devops => write!(f, "devops"),
            AgentType::Security => write!(f, "security"),
            AgentType::Database => write!(f, "database"),
            AgentType::Network => write!(f, "network"),
            AgentType::Support => write!(f, "support"),
        }
    }
}

/// Hire (deploy) an AI agent to a server
#[derive(Debug, Parser, Clone)]
pub struct HireCommand {
    /// Type of agent to deploy
    #[arg(value_enum)]
    pub agent_type: AgentType,

    /// Target server ID for deployment
    #[arg(long, short = 's')]
    pub server: String,

    /// Agent display name
    #[arg(long, short = 'n')]
    pub name: Option<String>,

    /// Agent capabilities (comma-separated)
    #[arg(long, short = 'c', value_delimiter = ',')]
    pub capabilities: Option<Vec<String>>,

    /// Skip confirmation prompt
    #[arg(long, short = 'y')]
    pub yes: bool,

    /// Output format: table, json
    #[arg(long, default_value = "table")]
    pub format: String,
}

impl HireCommand {
    pub fn run(self) -> Result<()> {
        #[cfg(feature = "hrm")]
        {
            run_hire_with_hrm(self)
        }

        #[cfg(not(feature = "hrm"))]
        {
            println!(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            );
            println!("  🔒 HRM AI Premium Feature");
            println!(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            );
            println!();
            println!("  The 'hire' command requires the HRM AI premium module.");
            println!();
            println!("  To enable HRM AI capabilities, rebuild with:");
            println!("    cargo build --features hrm");
            println!();
            println!("  HRM AI Features:");
            println!("    • cx hire <agent-type>  - Deploy AI agents");
            println!("    • cx fire <agent-id>    - Terminate agents");
            println!("    • PostgreSQL integration for fleet management");
            println!("    • Enterprise compliance automation");
            println!();
            println!("  License: BSL 1.1 (Business Source License)");
            println!(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            );
            Ok(())
        }
    }
}

#[cfg(feature = "hrm")]
fn run_hire_with_hrm(cmd: HireCommand) -> Result<()> {
    use tokio::runtime::Runtime;

    let rt = Runtime::new()?;
    rt.block_on(async {
        let theme = SovereignTheme::new();

        // Print header
        theme.print_header("CX Linux Agent Deployment");

        println!();
        println!("  📋 Deployment Request");
        println!("  ─────────────────────────────────────");
        println!("  Agent Type:  {}", cmd.agent_type);
        println!("  Server:      {}", cmd.server);
        if let Some(ref name) = cmd.name {
            println!("  Name:        {}", name);
        }
        if let Some(ref caps) = cmd.capabilities {
            println!("  Capabilities: {}", caps.join(", "));
        }
        println!();

        // Confirm unless --yes
        if !cmd.yes {
            print!("  Deploy this agent? [y/N] ");
            std::io::Write::flush(&mut std::io::stdout())?;

            let mut input = String::new();
            std::io::stdin().read_line(&mut input)?;

            if !input.trim().eq_ignore_ascii_case("y") {
                println!("  ❌ Deployment cancelled");
                return Ok(());
            }
        }

        // Get database URL from environment
        let db_url = std::env::var("DATABASE_URL")
            .unwrap_or_else(|_| "postgres://localhost/cx_agents".to_string());

        // Create hiring service
        let config = HireConfig {
            database_url: db_url,
            default_capabilities: get_default_capabilities(&cmd.agent_type),
        };

        let service = AgentHiringService::new(config).await?;

        // Generate agent name if not provided
        let agent_name = cmd.name.unwrap_or_else(|| {
            format!(
                "{}-{}",
                cmd.agent_type,
                &uuid::Uuid::new_v4().to_string()[..8]
            )
        });

        // Deploy agent
        println!("  🚀 Deploying agent...");

        let agent = service
            .hire_agent(
                &agent_name,
                &cmd.agent_type.to_string(),
                &cmd.server,
                cmd.capabilities.unwrap_or_default(),
            )
            .await?;

        println!();
        theme.print_success(&format!("Agent deployed: {}", agent.id));
        println!();
        println!("  Agent ID:    {}", agent.id);
        println!("  Name:        {}", agent.name);
        println!("  Type:        {}", agent.agent_type);
        println!("  Server:      {}", agent.server_id);
        println!("  Status:      {:?}", agent.status);
        println!();

        Ok(())
    })
}

#[cfg(feature = "hrm")]
fn get_default_capabilities(agent_type: &AgentType) -> Vec<String> {
    match agent_type {
        AgentType::Devops => vec![
            "deploy".into(),
            "rollback".into(),
            "scale".into(),
            "monitor".into(),
        ],
        AgentType::Security => vec![
            "audit".into(),
            "scan".into(),
            "patch".into(),
            "firewall".into(),
        ],
        AgentType::Database => vec![
            "backup".into(),
            "restore".into(),
            "optimize".into(),
            "migrate".into(),
        ],
        AgentType::Network => vec![
            "configure".into(),
            "diagnose".into(),
            "loadbalance".into(),
            "dns".into(),
        ],
        AgentType::Support => vec![
            "ticket".into(),
            "escalate".into(),
            "notify".into(),
            "report".into(),
        ],
    }
}
