/**
 * R16 contract tests for the Catalog + Policy editor page.
 *
 * Fixtures in __fixtures__/ were captured from the real backend
 * (recette.api on port 8092): /catalog/actions, /policies, /policies/active.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogFixture from "./__fixtures__/catalog.fixture.json";
import policiesFixture from "./__fixtures__/policies.fixture.json";
import activePolicyFixture from "./__fixtures__/policy-active.fixture.json";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    getCatalog: vi.fn(),
    listPolicies: vi.fn(),
    getActivePolicy: vi.fn(),
    publishPolicy: vi.fn(),
    setActivePolicy: vi.fn(),
  };
});

import * as client from "../../api/client";
import type { ActionSpec, PolicyDocument } from "../../types/platform";
import CatalogPage from "./index";

const mockedGetCatalog = vi.mocked(client.getCatalog);
const mockedListPolicies = vi.mocked(client.listPolicies);
const mockedGetActivePolicy = vi.mocked(client.getActivePolicy);
const mockedPublishPolicy = vi.mocked(client.publishPolicy);
const mockedSetActivePolicy = vi.mocked(client.setActivePolicy);

// The real backend wraps payloads; the client is typed as bare arrays, so the
// fixtures are passed through the mocked client exactly as the backend sends them.
const catalogPayload = catalogFixture as unknown as ActionSpec[];
const policiesPayload = policiesFixture as unknown as { versions: string[]; active: string | null };
const activePolicy = activePolicyFixture as unknown as PolicyDocument;

beforeEach(() => {
  vi.clearAllMocks();
  mockedGetCatalog.mockResolvedValue(catalogPayload);
  mockedListPolicies.mockResolvedValue(policiesPayload);
  mockedGetActivePolicy.mockResolvedValue(activePolicy);
  mockedPublishPolicy.mockImplementation((doc) => Promise.resolve(doc));
  mockedSetActivePolicy.mockResolvedValue(activePolicy);
});

describe("CatalogPage", () => {
  it("renders the full catalog with the total count of 118", async () => {
    render(<CatalogPage />);

    const count = await screen.findByTestId("catalog-count");
    expect(count).toHaveTextContent("118 of 118 actions");
    expect(catalogFixture.count).toBe(118);

    // Header row + 118 data rows.
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(1 + 118);
  });

  it("renders the okta suspend_user row with its risk badge", async () => {
    render(<CatalogPage />);

    const description = await screen.findByText("Suspend an Okta user account.");
    const row = description.closest("tr");
    expect(row).not.toBeNull();
    const scoped = within(row as HTMLTableRowElement);
    expect(scoped.getByText("okta")).toBeInTheDocument();
    expect(scoped.getByText("suspend_user")).toBeInTheDocument();
    const riskBadge = scoped.getByText("high");
    expect(riskBadge).toHaveClass("badge", "badge-high");
    expect(scoped.getByText("escalate")).toHaveClass("badge-escalate");
    expect(scoped.getByText("deny")).toHaveClass("badge-deny");
  });

  it("filters rows by target_system", async () => {
    render(<CatalogPage />);
    await screen.findByTestId("catalog-count");

    const allRows = screen.getAllByRole("row");
    expect(allRows).toHaveLength(1 + 118);

    fireEvent.change(screen.getByLabelText("Target system"), {
      target: { value: "github" },
    });

    const githubCount = catalogFixture.actions.filter(
      (a) => a.target_system === "github",
    ).length;
    expect(githubCount).toBeGreaterThan(0);
    expect(githubCount).toBeLessThan(118);

    const filteredRows = screen.getAllByRole("row");
    expect(filteredRows).toHaveLength(1 + githubCount);
    expect(screen.getByTestId("catalog-count")).toHaveTextContent(
      `${githubCount} of 118 actions`,
    );
  });

  it("shows the active policy version v1 with its rule count", async () => {
    render(<CatalogPage />);

    const version = await screen.findByTestId("active-policy-version");
    expect(version).toHaveTextContent("v1");
    expect(screen.getByTestId("active-policy-rule-count")).toHaveTextContent(
      `${activePolicyFixture.rules.length} rules`,
    );
    expect(activePolicyFixture.rules.length).toBe(111);
  });

  it("publishes an edited policy as a new version and activates it", async () => {
    render(<CatalogPage />);
    await screen.findByTestId("active-policy-version");

    fireEvent.click(screen.getByRole("button", { name: "Edit policy" }));

    const firstRule = activePolicyFixture.rules[0];
    const ruleSelect = screen.getByLabelText(`Verdict for ${firstRule.rule_id}`);
    fireEvent.change(ruleSelect, { target: { value: "deny" } });

    fireEvent.change(screen.getByLabelText("New version"), {
      target: { value: "v2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Publish as new version" }));

    await waitFor(() => {
      expect(mockedPublishPolicy).toHaveBeenCalledTimes(1);
    });
    const published = mockedPublishPolicy.mock.calls[0][0];
    expect(published.version).toBe("v2");
    expect(published.default).toBe("deny");
    expect(published.approval_timeout_seconds).toBe(
      activePolicyFixture.approval_timeout_seconds,
    );
    expect(published.rules).toHaveLength(activePolicyFixture.rules.length);
    expect(published.rules[0].rule_id).toBe(firstRule.rule_id);
    expect(published.rules[0].verdict).toBe("deny");
    expect(mockedSetActivePolicy).toHaveBeenCalledWith("v2");
  });

  it("renders an error banner when the catalog request fails", async () => {
    mockedGetCatalog.mockRejectedValue(new Error("network unreachable"));

    render(<CatalogPage />);

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("network unreachable");
  });

  it("renders an error banner on a 409 duplicate version without crashing", async () => {
    mockedPublishPolicy.mockRejectedValue(
      new client.ApiError(409, "/policies", "policy version 'v1' is immutable"),
    );

    render(<CatalogPage />);
    await screen.findByTestId("active-policy-version");

    fireEvent.click(screen.getByRole("button", { name: "Edit policy" }));
    fireEvent.change(screen.getByLabelText("New version"), {
      target: { value: "v1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Publish as new version" }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Version conflict (409)");
    expect(mockedSetActivePolicy).not.toHaveBeenCalled();
    // The editor stays open so the operator can pick another version.
    expect(
      screen.getByRole("button", { name: "Publish as new version" }),
    ).toBeInTheDocument();
  });
});
