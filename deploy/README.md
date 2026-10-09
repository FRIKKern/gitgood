# Barkpark Cloud application contract

This is a design contract, not a deployable package.

Gitgood owns its web/API release packaging, migrations, version/readiness endpoints, functional probes, and app-specific data requirements. Cloud owns generic validation, provisioning, inventory, routing, constrained lifecycle execution, and reporting.

The [controlled native upgrade work](../docs/implementation/installation-upgrade.md)
includes digest-bound artifact inspection, controlled installed activation and
explicit failure recovery. These local operator experiments do not establish
managed Cloud deployment.

The proposed descriptor must declare immutable artifact digests, target CPU/runtime, service/private-network dependencies, database and volume bindings, secret references, HTTP/SSH routes, owner bootstrap, migrations, health gates, backup/restore, and upgrade compatibility.

The inspected Cloud Node path expects Next.js standalone output. Prototype actual TanStack output rather than claiming existing support. The current archive path covers Barkpark database/media; Git repositories and other adopted stores need explicit lifecycle support.

Do not grant a deployment descriptor unrestricted host shell execution. Use reviewed lifecycle actions and scoped credentials. Store code releases separately from mutable customer data.

D06 proves clean-host packaging; D07 proves coordinated restoration. Keep source-derived templates and service manifests minimal until these experiments establish the contract.
