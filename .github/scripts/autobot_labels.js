class AutobotLabelRegistry {
  static MAX_AUTOBOT_LABELS = 12;

  static LABEL_GUIDANCE = Object.freeze({
    "breaking-change": "Use when consumers must adapt because of an incompatible API, contract, config, or behavior change.",
    "security": "Use when auth, permissions, secrets, sanitization, or exploit mitigation clearly changed.",
    "api": "Use when endpoints, handlers, or request or response contracts changed.",
    "database": "Use when migrations, queries, schema storage, or database configuration materially changed.",
    "schema": "Use when shared schema artifacts such as GraphQL, JSON Schema, or Proto changed.",
    "compatibility": "Use when interoperability, backward compatibility, or adapter behavior changed.",
    "migration": "Use when upgrade steps, migration scripts, or transition logic changed.",
    "feature-flag": "Use when rollout toggles or gated behavior changed.",
    "runtime": "Use when runtime support, platform execution behavior, or environment compatibility changed.",
    "performance": "Use only when the summary explicitly supports speed, caching, latency, or memory effects.",
    "bug": "Use when the summary clearly describes incorrect behavior, failure, regression, or a broken path.",
    "enhancement": "Use when the change adds or expands meaningful capability.",
    "improvement": "Use mainly for issues that request a meaningful improvement or gap closure without a confirmed defect.",
    "proposal": "Use mainly for issues that describe a proposed direction or future work.",
    "documentation": "Use when documentation is a substantial part of the actual work.",
    "test": "Use when tests or test harnesses are added, changed, or repaired.",
    "workflow": "Use when GitHub workflow orchestration or job logic changed.",
    "automation": "Use when bot or autonomous repository automation behavior changed.",
    "github": "Use when GitHub-specific repository metadata, templates, or repo automation surfaces changed.",
    "ci": "Use when pipeline execution or validation job behavior changed.",
    "config": "Use when settings, manifests, or environment configuration changed.",
    "dependencies": "Use when dependencies, lockfiles, or package manifests changed.",
    "docker": "Use when Docker image or compose configuration changed.",
    "tooling": "Use when developer tools or scripts materially changed.",
    "dx": "Use when the main outcome is smoother local development workflow.",
    "cleanup": "Use when obsolete code or files were intentionally removed.",
    "chore": "Use only for small maintenance work that lacks a stronger label."
  });

  static DEFAULT_ISSUE_LABELS = Object.freeze([
    "bug",
    "enhancement",
    "improvement",
    "proposal",
    "documentation",
    "security",
    "performance",
    "api",
    "database",
    "schema",
    "compatibility",
    "migration",
    "runtime",
    "config",
    "workflow",
    "github",
    "test"
  ]);

  static LABEL_DEFINITIONS = Object.freeze({
    "bug": Object.freeze({ color: "d73a4a", description: "Something isn't working" }),
    "enhancement": Object.freeze({ color: "a2eeef", description: "New feature or request" }),
    "improvement": Object.freeze({ color: "a2eeef", description: "Improvement request or capability expansion" }),
    "proposal": Object.freeze({ color: "bfd4f2", description: "Proposed future work or product change" }),
    "documentation": Object.freeze({ color: "0075ca", description: "Improvements or additions to documentation" }),
    "breaking-change": Object.freeze({ color: "b60205", description: "Incompatible API changes" }),
    "ui": Object.freeze({ color: "d4c5f9", description: "Visual or UI/UX improvements" }),
    "performance": Object.freeze({ color: "5319e7", description: "Performance improvements" }),
    "security": Object.freeze({ color: "e30c0c", description: "Security fixes and updates" }),
    "refactor": Object.freeze({ color: "f29513", description: "Code change that neither fixes a bug nor adds a feature" }),
    "test": Object.freeze({ color: "cc317c", description: "Adding, missing, or correcting tests" }),
    "ci": Object.freeze({ color: "006b75", description: "CI/CD and workflow updates" }),
    "dependencies": Object.freeze({ color: "0366d6", description: "Dependency updates" }),
    "database": Object.freeze({ color: "fbca04", description: "Database migrations or schema changes" }),
    "build": Object.freeze({ color: "89590b", description: "Build system and tooling updates" }),
    "accessibility": Object.freeze({ color: "c2e0c6", description: "Accessibility (a11y) improvements" }),
    "localization": Object.freeze({ color: "91d674", description: "Localization (i18n) and translation" }),
    "api": Object.freeze({ color: "1d76db", description: "API endpoint or schema changes" }),
    "infrastructure": Object.freeze({ color: "5e4a80", description: "Cloud infrastructure and IaC changes" }),
    "config": Object.freeze({ color: "c5def5", description: "Configuration and environment changes" }),
    "types": Object.freeze({ color: "2b67c6", description: "Type definitions and schema changes" }),
    "logging": Object.freeze({ color: "bfdadc", description: "Logging, monitoring, and observability" }),
    "deprecation": Object.freeze({ color: "ffa500", description: "Deprecated features with migration paths" }),
    "chore": Object.freeze({ color: "ededed", description: "Maintenance tasks and cleanup" }),
    "dx": Object.freeze({ color: "0e8a16", description: "Developer experience improvements" }),
    "release": Object.freeze({ color: "1d76db", description: "Release/versioning/packaging changes" }),
    "observability": Object.freeze({ color: "bfe5bf", description: "Metrics/tracing/alerts/monitoring setup" }),
    "docs-site": Object.freeze({ color: "bfd4f2", description: "Documentation site changes" }),
    "runtime": Object.freeze({ color: "7057ff", description: "Runtime/platform compatibility changes" }),
    "cleanup": Object.freeze({ color: "cfd3d7", description: "Dead code removal and cleanup" }),
    "style": Object.freeze({ color: "fef2c0", description: "Formatting-only changes" }),
    "lint": Object.freeze({ color: "fbca04", description: "Lint-only changes (rules/config/fixes)" }),
    "formatting": Object.freeze({ color: "fef2c0", description: "Formatting changes" }),
    "tooling": Object.freeze({ color: "c5def5", description: "Tooling/scripts/editor configuration changes" }),
    "release-notes": Object.freeze({ color: "1d76db", description: "Changelog/release notes updates" }),
    "versioning": Object.freeze({ color: "1d76db", description: "Version bumps of the project itself" }),
    "packaging": Object.freeze({ color: "1d76db", description: "Packaging/publishing configuration" }),
    "workflow": Object.freeze({ color: "006b75", description: "Workflow logic changes beyond basic CI" }),
    "automation": Object.freeze({ color: "006b75", description: "Automation/bots/scripts for repo management" }),
    "quality": Object.freeze({ color: "d4c5f9", description: "Maintainability/readability improvements" }),
    "stability": Object.freeze({ color: "d73a4a", description: "Reliability/flakiness reductions/hardening" }),
    "error-handling": Object.freeze({ color: "d73a4a", description: "Error handling improvements" }),
    "validation": Object.freeze({ color: "e99695", description: "Validation/schema/guard changes" }),
    "feature-flag": Object.freeze({ color: "c2e0c6", description: "Feature flags/rollout toggles" }),
    "migration": Object.freeze({ color: "fbca04", description: "Migrations/upgrade steps" }),
    "compatibility": Object.freeze({ color: "7057ff", description: "Compatibility work, shims, polyfills" }),
    "monitoring": Object.freeze({ color: "bfe5bf", description: "Monitoring/alerting/dashboards" }),
    "telemetry": Object.freeze({ color: "bfe5bf", description: "Analytics/telemetry instrumentation" }),
    "logging-verbosity": Object.freeze({ color: "bfdadc", description: "Log level/volume/fields changes" }),
    "docs-api": Object.freeze({ color: "0075ca", description: "API documentation changes" }),
    "examples": Object.freeze({ color: "bfd4f2", description: "Examples/sample code changes" }),
    "devcontainer": Object.freeze({ color: "c5def5", description: "Devcontainer/local env changes" }),
    "docker": Object.freeze({ color: "c5def5", description: "Docker/container changes" }),
    "kubernetes": Object.freeze({ color: "c5def5", description: "Kubernetes/Helm/Kustomize changes" }),
    "terraform": Object.freeze({ color: "c5def5", description: "Terraform changes" }),
    "helm": Object.freeze({ color: "c5def5", description: "Helm chart changes" }),
    "github": Object.freeze({ color: "0366d6", description: "GitHub templates/settings/codeowners changes" }),
    "policy": Object.freeze({ color: "0366d6", description: "Policy/governance/support/security policy changes" }),
    "license": Object.freeze({ color: "0366d6", description: "License/legal changes" }),
    "supply-chain": Object.freeze({ color: "e30c0c", description: "Supply chain hardening (SBOM/signing/provenance)" }),
    "codegen": Object.freeze({ color: "c5def5", description: "Code generation templates/config/output" }),
    "schema": Object.freeze({ color: "2b67c6", description: "Schema changes (proto/graphql/jsonschema)" }),
    "serialization": Object.freeze({ color: "2b67c6", description: "Serialization format changes" })
  });

  static LABEL_PRIORITY = Object.freeze([
    "breaking-change",
    "security",
    "api",
    "database",
    "schema",
    "compatibility",
    "migration",
    "feature-flag",
    "runtime",
    "performance",
    "enhancement",
    "improvement",
    "deprecation",
    "bug",
    "validation",
    "stability",
    "error-handling",
    "ui",
    "accessibility",
    "localization",
    "documentation",
    "docs-site",
    "docs-api",
    "examples",
    "test",
    "workflow",
    "ci",
    "automation",
    "github",
    "config",
    "dependencies",
    "docker",
    "devcontainer",
    "packaging",
    "build",
    "release",
    "release-notes",
    "versioning",
    "tooling",
    "dx",
    "refactor",
    "quality",
    "cleanup",
    "logging",
    "logging-verbosity",
    "observability",
    "monitoring",
    "telemetry",
    "policy",
    "supply-chain",
    "serialization",
    "types",
    "codegen",
    "infrastructure",
    "kubernetes",
    "terraform",
    "helm",
    "proposal",
    "style",
    "formatting",
    "lint",
    "chore"
  ]);

  static URGENT_SYNC_LABELS = Object.freeze(["breaking-change", "security"]);

  static VERSION_SENSITIVE_LABELS = Object.freeze([
    "breaking-change",
    "enhancement",
    "improvement",
    "deprecation",
    "security",
    "bug",
    "performance",
    "api",
    "database",
    "schema",
    "compatibility",
    "migration",
    "feature-flag",
    "runtime"
  ]);

  static RELEASE_CRITICAL_LABELS = Object.freeze([
    "breaking-change",
    "security",
    "api",
    "database",
    "schema",
    "compatibility",
    "migration",
    "feature-flag",
    "runtime",
    "performance"
  ]);

  static VERSION_LABEL_ALIASES = Object.freeze({ "breaking-changes": "breaking-change", "breaking_change": "breaking-change" });

  static FORCE_RELEASE_TYPES = Object.freeze(["enhancement", "breaking-change", "security"]);

  static RELEASE_RELEVANT_LABELS = Object.freeze([
    "api",
    "breaking-change",
    "bug",
    "compatibility",
    "database",
    "deprecation",
    "enhancement",
    "feature-flag",
    "improvement",
    "migration",
    "performance",
    "runtime",
    "schema",
    "security"
  ]);

  static SECONDARY_LABELS = Object.freeze([
    "chore",
    "ci",
    "cleanup",
    "config",
    "dependencies",
    "documentation",
    "dx",
    "formatting",
    "github",
    "lint",
    "quality",
    "refactor",
    "style",
    "test",
    "tooling",
    "workflow"
  ]);

  static GENERIC_FALLBACK_LABELS = Object.freeze(["config", "dependencies", "tooling", "dx", "cleanup", "chore"]);

  static MAJOR_VERSION_LABELS = Object.freeze(["breaking-change"]);

  static MINOR_VERSION_LABELS = Object.freeze(["deprecation", "enhancement", "improvement"]);

  static VALID_LABELS = new Set(Object.keys(AutobotLabelRegistry.LABEL_DEFINITIONS));

  static VERSION_BUMP_BY_LABEL = Object.freeze(
    Object.fromEntries(
      Object.keys(AutobotLabelRegistry.LABEL_DEFINITIONS).map((label) => {
        if (AutobotLabelRegistry.MAJOR_VERSION_LABELS.includes(label)) {
          return [label, "major"];
        }
        if (AutobotLabelRegistry.MINOR_VERSION_LABELS.includes(label)) {
          return [label, "minor"];
        }
        return [label, "patch"];
      })
    )
  );

  static normalizeLabelName(label) {
    const normalized = String(label || "").trim().toLowerCase();
    return AutobotLabelRegistry.VERSION_LABEL_ALIASES[normalized] || normalized;
  }

  static hasLabelName(labels, expectedLabel) {
    return (labels || []).some((label) => {
      const labelName = typeof label === "string" ? label : label?.name;
      return AutobotLabelRegistry.normalizeLabelName(labelName) === expectedLabel;
    });
  }

  static hasReleaseRelevantLabel(labels) {
    return AutobotLabelRegistry.RELEASE_RELEVANT_LABELS.some((label) => AutobotLabelRegistry.hasLabelName(labels, label));
  }

  static uniqueValidLabels(labels) {
    return [
      ...new Set(
        (labels || [])
          .map((label) => AutobotLabelRegistry.normalizeLabelName(label))
          .filter((label) => AutobotLabelRegistry.VALID_LABELS.has(label))
      )
    ];
  }

  static sortLabels(labels) {
    return [...new Set(labels)]
      .filter(Boolean)
      .sort((left, right) => {
        const leftRank = AutobotLabelRegistry.LABEL_PRIORITY.indexOf(left);
        const rightRank = AutobotLabelRegistry.LABEL_PRIORITY.indexOf(right);
        const normalizedLeftRank = leftRank === -1 ? AutobotLabelRegistry.LABEL_PRIORITY.length : leftRank;
        const normalizedRightRank = rightRank === -1 ? AutobotLabelRegistry.LABEL_PRIORITY.length : rightRank;
        return normalizedLeftRank - normalizedRightRank || left.localeCompare(right);
      });
  }

  static trimLowSignalLabels(labels, options = {}) {
    const limit = Math.max(Number(options.limit) || AutobotLabelRegistry.MAX_AUTOBOT_LABELS, 1);
    const uniqueLabels = AutobotLabelRegistry.uniqueValidLabels(labels);
    if (uniqueLabels.length <= 3) {
      return uniqueLabels.slice(0, limit);
    }
    const versionCritical = AutobotLabelRegistry.VERSION_SENSITIVE_LABELS.filter((label) => uniqueLabels.includes(label));
    const primary = uniqueLabels.filter((label) => !AutobotLabelRegistry.SECONDARY_LABELS.includes(label) && !versionCritical.includes(label));
    const secondary = uniqueLabels.filter((label) => AutobotLabelRegistry.SECONDARY_LABELS.includes(label));
    const cappedPrimary = [...versionCritical, ...primary].slice(0, limit);
    const remainingSlots = Math.max(limit - cappedPrimary.length, 0);
    const cappedSecondary = secondary.slice(0, remainingSlots);
    return [...cappedPrimary, ...cappedSecondary].slice(0, limit);
  }

  static parseAutobotLabels(raw) {
    if (!raw) {
      return [];
    }
    try {
      const cleaned = String(raw).replace(/```json\s*/gi, "").replace(/```\s*/gi, "").trim();
      const parsed = JSON.parse(cleaned);
      if (Array.isArray(parsed)) {
        return AutobotLabelRegistry.uniqueValidLabels(parsed);
      }
    } catch (error) {
      return AutobotLabelRegistry.uniqueValidLabels(
        String(raw)
          .replace(/[\[\]"'`]/g, "")
          .split(/[\n,]/)
      );
    }
    return [];
  }

  static labelNamesFromIssue(issue) {
    return AutobotLabelRegistry.uniqueValidLabels(
      (issue?.labels || []).map((label) => typeof label === "string" ? label : label.name)
    );
  }
}

const MAX_AUTOBOT_LABELS = AutobotLabelRegistry.MAX_AUTOBOT_LABELS;
const DEFAULT_ISSUE_LABELS = AutobotLabelRegistry.DEFAULT_ISSUE_LABELS;
const FORCE_RELEASE_TYPES = AutobotLabelRegistry.FORCE_RELEASE_TYPES;
const LABEL_DEFINITIONS = AutobotLabelRegistry.LABEL_DEFINITIONS;
const LABEL_GUIDANCE = AutobotLabelRegistry.LABEL_GUIDANCE;
const LABEL_PRIORITY = AutobotLabelRegistry.LABEL_PRIORITY;
const RELEASE_CRITICAL_LABELS = AutobotLabelRegistry.RELEASE_CRITICAL_LABELS;
const RELEASE_RELEVANT_LABELS = AutobotLabelRegistry.RELEASE_RELEVANT_LABELS;
const SECONDARY_LABELS = AutobotLabelRegistry.SECONDARY_LABELS;
const URGENT_SYNC_LABELS = AutobotLabelRegistry.URGENT_SYNC_LABELS;
const VALID_LABELS = AutobotLabelRegistry.VALID_LABELS;
const VERSION_BUMP_BY_LABEL = AutobotLabelRegistry.VERSION_BUMP_BY_LABEL;
const VERSION_LABEL_ALIASES = AutobotLabelRegistry.VERSION_LABEL_ALIASES;
const VERSION_SENSITIVE_LABELS = AutobotLabelRegistry.VERSION_SENSITIVE_LABELS;

function hasLabelName(labels, expectedLabel) {
  return AutobotLabelRegistry.hasLabelName(labels, expectedLabel);
}

function hasReleaseRelevantLabel(labels) {
  return AutobotLabelRegistry.hasReleaseRelevantLabel(labels);
}

function labelNamesFromIssue(issue) {
  return AutobotLabelRegistry.labelNamesFromIssue(issue);
}

function normalizeLabelName(label) {
  return AutobotLabelRegistry.normalizeLabelName(label);
}

function parseAutobotLabels(raw) {
  return AutobotLabelRegistry.parseAutobotLabels(raw);
}

function sortLabels(labels) {
  return AutobotLabelRegistry.sortLabels(labels);
}

function trimLowSignalLabels(labels, options) {
  return AutobotLabelRegistry.trimLowSignalLabels(labels, options);
}

function uniqueValidLabels(labels) {
  return AutobotLabelRegistry.uniqueValidLabels(labels);
}

module.exports = {
  AutobotLabelRegistry,
  DEFAULT_ISSUE_LABELS,
  FORCE_RELEASE_TYPES,
  LABEL_DEFINITIONS,
  LABEL_GUIDANCE,
  LABEL_PRIORITY,
  MAX_AUTOBOT_LABELS,
  RELEASE_CRITICAL_LABELS,
  RELEASE_RELEVANT_LABELS,
  SECONDARY_LABELS,
  URGENT_SYNC_LABELS,
  VALID_LABELS,
  VERSION_BUMP_BY_LABEL,
  VERSION_LABEL_ALIASES,
  VERSION_SENSITIVE_LABELS,
  hasLabelName,
  hasReleaseRelevantLabel,
  labelNamesFromIssue,
  normalizeLabelName,
  parseAutobotLabels,
  sortLabels,
  trimLowSignalLabels,
  uniqueValidLabels
};