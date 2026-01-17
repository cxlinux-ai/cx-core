# Frequently Asked Questions

## General

**Q: What is Cortex Linux?**
A: An AI-native operating system that understands natural language. No more Stack Overflow, no more dependency hell.

**Q: Is it ready to use?**
A: MVP is 95% complete (November 2025). Demo-ready, production release coming soon.

**Q: What platforms does it support?**
A: Ubuntu 24.04 LTS currently. Other Debian-based distros coming soon.

**Q: Is it free?**
A: Free for personal use on 1 system (BUSL-1.1 license). Commercial use requires a subscription. See [pricing](https://cortexlinux.com/pricing).

## Usage

**Q: How do I install software?**
A: Just tell Cortex what you need:
```bash
cortex install "python for machine learning"
cortex install "web development environment"
```

**Q: What if something goes wrong?**
A: Cortex has automatic rollback:
```bash
cortex rollback
```

**Q: Can I test before installing?**
A: Yes, simulation mode:
```bash
cortex simulate "install oracle database"
```

**Q: Does it work with existing package managers?**
A: Yes, Cortex wraps apt/yum/dnf. Your existing commands still work.

## Contributing

**Q: How do I contribute?**
A: Browse issues, claim one, submit PR. See [Contributing](Contributing).

**Q: Do you pay for contributions?**
A: Yes! Cash bounties on merge. See [Bounty Program](Bounties).

**Q: How much can I earn?**
A: $25-200 per feature, plus 2x bonus at funding.

**Q: What skills do you need?**
A: Python, Linux systems, DevOps, AI/ML, or technical writing.

**Q: Can non-developers contribute?**
A: Yes! Documentation, testing, design, community management.

## Technical

**Q: What AI model does it use?**
A: Claude (Anthropic) for natural language understanding.

**Q: Is it secure?**
A: Yes. Firejail sandboxing + AppArmor policies. AI actions are validated before execution.

**Q: Does it phone home?**
A: Only for AI API calls. No telemetry. Enterprise can run air-gapped with local LLMs.

**Q: Can I use my own LLM?**
A: Coming soon. Plugin system will support local models.

**Q: What's the overhead?**
A: Minimal. AI calls only during installation planning. Execution is native Linux.

## Business

**Q: Who's behind this?**
A: Michael J. Morgan (CEO), AI Venture Holdings LLC. Patent holder in AI systems.

**Q: What's the business model?**
A: Open source community + Enterprise subscriptions (like Red Hat).

**Q: Are you hiring?**
A: Yes! Top contributors may join the founding team. See [Contributing](Contributing).

**Q: When is the seed round?**
A: February 2025 ($2-3M target).

**Q: Can I invest?**
A: Contact mike@cortexlinux.com for investor information.

## Support

**Q: Where do I get help?**
A: Discord: https://discord.gg/uCqHvxjU83

**Q: How do I report bugs?**
A: GitHub Issues: https://github.com/cortexlinux/cortex/issues

**Q: Is there documentation?**
A: Yes! This wiki + in-code docs.

**Q: Can I request features?**
A: Yes! GitHub Discussions or Discord.

## More Questions?

Ask in [Discord](https://discord.gg/uCqHvxjU83) or open a [Discussion](https://github.com/cortexlinux/cortex/discussions).
