/*
 * Copyright (c) 2026 CX Linux
 * Licensed under the Business Source License 1.1
 * You may not use this file except in compliance with the License.
 */

//! HRM AI Agent Termination Command
//!
//! Safely terminates AI agents with confirmation and audit logging.
//! This module is only available when the `hrm` feature is enabled.
//!
//! # Example
//! ```bash
//! # Terminate an agent by ID
//! cx fire abc123-def456
//!
//! # Force termination (skip confirmation)
//! cx fire abc123-def456 --force
//!
//! # Terminate with reason
//! cx fire abc123-def456 --reason "Migrating to new server"
//! ```

use anyhow::Result;
use clap::Parser;

#[cfg(feature = "hrm")]
use hrm_ai::{
    database::AgentRepository,
    fire::{AgentTerminationService, TerminationConfig},
    theme::SovereignTheme,
};

/// Terminate (fire) an AI agent
#[derive(Debug, Parser, Clone)]
pub struct FireCommand {
    /// Agent ID to terminate
    pub agent_id: String,

    /// Skip confirmation prompt (dangerous)
    #[arg(long, short = 'f')]
    pub force: bool,

    /// Reason for termination (for audit log)
    #[arg(long, short = 'r')]
    pub reason: Option<String>,

    /// Graceful shutdown timeout in seconds
    #[arg(long, default_value = "30")]
    pub timeout: u64,

    /// Output format: table, json
    #[arg(long, default_value = "table")]
    pub format: String,
}

impl FireCommand {
    pub fn run(self) -> Result<()> {
        #[cfg(feature = "hrm")]
        {
            run_fire_with_hrm(self)
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
            println!("  The 'fire' command requires the HRM AI premium module.");
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
fn run_fire_with_hrm(cmd: FireCommand) -> Result<()> {
    use std::time::Duration;
    use tokio::runtime::Runtime;

    let rt = Runtime::new()?;
    rt.block_on(async {
        let theme = SovereignTheme::new();

        // Print header
        theme.print_header("CX Linux Agent Termination");

        // Get database URL from environment
        let db_url = std::env::var("DATABASE_URL")
            .unwrap_or_else(|_| "postgres://localhost/cx_agents".to_string());

        // Create repository to fetch agent info
        let repo = AgentRepository::new(&db_url).await?;

        // Fetch agent details
        let agent = match repo.get_agent(&cmd.agent_id).await? {
            Some(a) => a,
            None => {
                theme.print_error(&format!("Agent not found: {}", cmd.agent_id));
                return Ok(());
            }
        };

        println!();
        println!("  ⚠️  Termination Request");
        println!("  ─────────────────────────────────────");
        println!("  Agent ID:    {}", agent.id);
        println!("  Name:        {}", agent.name);
        println!("  Type:        {}", agent.agent_type);
        println!("  Server:      {}", agent.server_id);
        println!("  Status:      {:?}", agent.status);
        if let Some(ref reason) = cmd.reason {
            println!("  Reason:      {}", reason);
        }
        println!();

        // Require confirmation unless --force
        if !cmd.force {
            println!("  ⚠️  WARNING: This action cannot be undone!");
            println!();
            print!("  Type the agent name to confirm termination: ");
            std::io::Write::flush(&mut std::io::stdout())?;

            let mut input = String::new();
            std::io::stdin().read_line(&mut input)?;

            if input.trim() != agent.name {
                println!();
                println!("  ❌ Termination cancelled - name mismatch");
                return Ok(());
            }
        }

        // Create termination service
        let config = TerminationConfig {
            database_url: db_url,
            graceful_timeout: Duration::from_secs(cmd.timeout),
            audit_enabled: true,
        };

        let service = AgentTerminationService::new(config).await?;

        // Terminate agent
        println!();
        println!("  🔥 Initiating graceful shutdown...");

        let reason = cmd
            .reason
            .unwrap_or_else(|| "Manual termination".to_string());
        let result = service.terminate_agent(&cmd.agent_id, &reason).await?;

        if result.success {
            println!();
            theme.print_success("Agent terminated successfully");
            println!();
            println!("  Agent ID:       {}", cmd.agent_id);
            println!("  Shutdown Time:  {}ms", result.shutdown_duration_ms);
            println!("  Audit ID:       {}", result.audit_id);
            println!();

            if result.tasks_migrated > 0 {
                println!(
                    "  📋 {} pending tasks migrated to other agents",
                    result.tasks_migrated
                );
            }
        } else {
            theme.print_error("Termination failed");
            if let Some(error) = result.error {
                println!("  Error: {}", error);
            }
        }

        Ok(())
    })
}
