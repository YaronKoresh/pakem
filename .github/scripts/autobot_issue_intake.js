const { scoreDeterministicEvidence } = require("./autobot_deterministic_scorer");
const { AutobotLabelRegistry } = require("./autobot_labels");

class AutobotIssueClassifier {
  static ISSUE_RELEASE_RELEVANT_LABELS = new Set(["bug", ...AutobotLabelRegistry.RELEASE_CRITICAL_LABELS]);

  static TEMPLATE_MARKERS = Object.freeze({
    documentation: Object.freeze([
      "documentation issue report",
      "link(s) to the affected documentation",
      "detailed description of the problem",
      "proposed solution (optional)"
    ]),
    bug: Object.freeze([
      "thank you for helping us squash this bug",
      "detailed steps to reproduce",
      "potential causes / workarounds / related issues (optional)",
      "custom modifications / configuration"
    ]),
    feature: Object.freeze([
      "proposing an improvement or enhancement",
      "current situation and problem/opportunity",
      "proposed improvement/enhancement",
      "potential costs, challenges, and considerations",
      "alternatives considered (optional)",
      "proposed steps or implementation plan (optional)"
    ])
  });

  static normalizeIssue(issue) {
    const title = String(issue?.title || "").trim();
    const body = String(issue?.body || "").trim();
    const text = `${title}\n${body}`.toLowerCase();
    return {
      title,
      body,
      text,
      normalizedTitle: title.toLowerCase(),
      normalizedBody: body.toLowerCase()
    };
  }

  static hasAnyMarker(text, markers) {
    return markers.some((marker) => text.includes(marker));
  }

  static pushUnique(items, value) {
    if (value && !items.includes(value)) {
      items.push(value);
    }
  }

  static pushEvidenceItem(items, ruleId) {
    if (ruleId && !items.some((item) => item.ruleId === ruleId)) {
      items.push({ ruleId });
    }
  }

  static scoredLabelNames(entries) {
    return (entries || []).map((entry) => String(entry?.label || "").trim()).filter(Boolean);
  }

  static hasScoredLabel(scoring, label, flagName = "emitted") {
    return Boolean(scoring?.labelScores?.[label]?.[flagName]);
  }

  static analyzeIssueIntake(issue) {
    const normalized = AutobotIssueClassifier.normalizeIssue(issue);
    const evidenceSignals = [];
    const likelyClassification = [];

    const documentationTemplate = AutobotIssueClassifier.hasAnyMarker(normalized.text, AutobotIssueClassifier.TEMPLATE_MARKERS.documentation);
    const bugTemplate = AutobotIssueClassifier.hasAnyMarker(normalized.text, AutobotIssueClassifier.TEMPLATE_MARKERS.bug);
    const featureTemplate = AutobotIssueClassifier.hasAnyMarker(normalized.text, AutobotIssueClassifier.TEMPLATE_MARKERS.feature);

    const documentationSignal = documentationTemplate || /\b(docs?|documentation|readme)\b/.test(normalized.normalizedTitle);
    const bugSignal = bugTemplate || /\b(bug|crash|error|failure|broken|regression)\b/.test(normalized.normalizedTitle);
    const enhancementSignal = featureTemplate || /\b(feature request|enhancement)\b/.test(normalized.normalizedTitle);
    const proposalSignal = /\b(proposal|rfc|request for comments|design proposal|roadmap|future work)\b/.test(normalized.normalizedTitle)
      || /\brequest for comments\b/.test(normalized.text);
    const improvementSignal = /\b(improvement|improve|streamline|simplify|quality of life|qol)\b/.test(normalized.normalizedTitle)
      || /\b(pain point|gap closure|quality of life)\b/.test(normalized.text);
    const runtimeSignal = /\b(runtime|windows|linux|macos|cuda|python)\b/.test(normalized.text);
    const apiSignal = /\b(api|endpoint|webhook|request|response)\b/.test(normalized.text);

    if (documentationTemplate) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "Structured documentation issue template fields are present.");
    }
    if (bugTemplate) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "Structured bug-report fields are present.");
    }
    if (featureTemplate) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "Structured feature-request fields are present.");
    }
    if (runtimeSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake mentions runtime or platform context.");
    }
    if (apiSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake mentions API context.");
    }

    const labels = [];
    if (documentationSignal) {
      AutobotIssueClassifier.pushUnique(labels, "documentation");
      AutobotIssueClassifier.pushUnique(likelyClassification, "documentation");
    } else if (bugSignal) {
      AutobotIssueClassifier.pushUnique(labels, "bug");
      AutobotIssueClassifier.pushUnique(likelyClassification, "bug");
    } else if (enhancementSignal || proposalSignal || improvementSignal) {
      AutobotIssueClassifier.pushUnique(labels, "enhancement");
      AutobotIssueClassifier.pushUnique(likelyClassification, "enhancement");
      if (proposalSignal) {
        AutobotIssueClassifier.pushUnique(labels, "proposal");
        AutobotIssueClassifier.pushUnique(likelyClassification, "proposal");
      } else if (improvementSignal) {
        AutobotIssueClassifier.pushUnique(labels, "improvement");
        AutobotIssueClassifier.pushUnique(likelyClassification, "improvement");
      }
    }

    if (documentationSignal && /\bproblem|incorrect|missing|unclear|outdated\b/.test(normalized.text)) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake describes a documentation defect or gap.");
    }
    if (bugSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake explicitly describes incorrect behavior or a failure.");
    }
    if (enhancementSignal || proposalSignal || improvementSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake asks for new or improved behavior rather than reporting a confirmed defect.");
    }
    if (proposalSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake frames the request as a proposal or future design direction.");
    }
    if (improvementSignal && !proposalSignal) {
      AutobotIssueClassifier.pushUnique(evidenceSignals, "The intake frames the request as a targeted improvement or gap closure.");
    }

    const evidenceItems = [];
    if (documentationSignal) {
      AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-documentation-report");
    } else if (bugSignal) {
      AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-bug-report");
    } else if (enhancementSignal || proposalSignal || improvementSignal) {
      AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-enhancement-request");
      if (proposalSignal) {
        AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-proposal-request");
      } else if (improvementSignal) {
        AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-improvement-request");
      }
    }
    if (runtimeSignal) {
      AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-runtime-context");
    }
    if (apiSignal) {
      AutobotIssueClassifier.pushEvidenceItem(evidenceItems, "issue-api-context");
    }

    const deterministicScoring = scoreDeterministicEvidence({ evidenceItems });
    const deterministicLabels = AutobotIssueClassifier.scoredLabelNames(deterministicScoring.emittedLabels);
    const deterministicPrimaryLabels = AutobotIssueClassifier.scoredLabelNames(deterministicScoring.primaryLabels);

    return {
      title: normalized.title,
      body: normalized.body,
      text: normalized.text,
      labels: labels.length > 0
        ? labels
        : [
            ...(AutobotIssueClassifier.hasScoredLabel(deterministicScoring, "runtime", "retained") ? ["runtime"] : []),
            ...(AutobotIssueClassifier.hasScoredLabel(deterministicScoring, "api", "retained") ? ["api"] : [])
          ],
      evidenceSignals,
      evidenceItems,
      likelyClassification,
      deterministicLabels,
      deterministicPrimaryLabels,
      deterministicSemver: deterministicScoring.semver,
      releaseRelevant: deterministicLabels.some((label) => AutobotIssueClassifier.ISSUE_RELEASE_RELEVANT_LABELS.has(label))
        || /\b(bug|regression|security|runtime|breaking|migration|database|schema|api)\b/.test(normalized.text)
    };
  }
}

function analyzeIssueIntake(issue) {
  return AutobotIssueClassifier.analyzeIssueIntake(issue);
}

module.exports = {
  AutobotIssueClassifier,
  analyzeIssueIntake
};