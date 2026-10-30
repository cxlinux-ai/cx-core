//! Small Tokio helper for CLI commands that need reqwest/async I/O outside the mux executor.

use anyhow::Context;

pub fn block_on_async(
    fut: impl std::future::Future<Output = anyhow::Result<()>>,
) -> anyhow::Result<()> {
    let rt = tokio::runtime::Runtime::new().context("Failed to start async runtime")?;
    rt.block_on(fut)
}
