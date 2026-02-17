//! CX Daemon shared library
//!
//! Provides shared utilities for the daemon and CLI

pub mod paths;

pub use paths::{get_alert_db_path, get_daemon_socket_path};
