/**
 * R16 contract test: the receipts page renders content-free receipts (intent +
 * size/digest) against a REAL captured /proxy/receipts payload, and never the
 * bodies.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import receiptsFixture from "./__fixtures__/receipts.fixture.json";
import type { ReceiptsResponse } from "../../types/platform";

vi.mock("../../api/client", () => ({
  getContextReceipts: vi.fn(),
  verifyContextReceipts: vi.fn(),
  exportContextReceipts: vi.fn(),
  verifyImportedReceipts: vi.fn(),
}));

import {
  getContextReceipts,
  verifyContextReceipts,
  verifyImportedReceipts,
} from "../../api/client";
import ReceiptsPage from "./index";

const fixture = receiptsFixture as unknown as ReceiptsResponse;
const verify = { ok: true, checked: fixture.receipts.length, first_break_seq: null, detail: null };

describe("ReceiptsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the content-free receipts (intent + size/digest, no bodies) + chain badge", async () => {
    vi.mocked(getContextReceipts).mockResolvedValue(fixture);
    vi.mocked(verifyContextReceipts).mockResolvedValue(verify);
    render(<ReceiptsPage />);

    const table = await screen.findByTestId("receipts-table");
    const first = fixture.receipts[0];
    expect(within(table).getByText(first.action_type!)).toBeInTheDocument();
    // The body byte-size is surfaced (privacy-safe digest, never the body).
    expect(within(table).getAllByText(`${first.request_bytes} o`).length).toBeGreaterThan(0);
    // The digest is shown truncated; the full sha is in the title attribute.
    expect(within(table).getAllByTitle(first.request_sha256).length).toBeGreaterThan(0);
    // The hash-chain integrity badge reports the verified sequence.
    expect(await screen.findByTestId("receipts-chain")).toHaveTextContent(/chaine verifiee/);
    // The signed-export action is offered (downloads the Ed25519 envelope).
    expect(screen.getByRole("button", { name: /Exporter \(signe/ })).toBeEnabled();
  });

  it("cross-verifies an imported third-party export and surfaces the verdict", async () => {
    vi.mocked(getContextReceipts).mockResolvedValue(fixture);
    vi.mocked(verifyContextReceipts).mockResolvedValue(verify);
    vi.mocked(verifyImportedReceipts).mockResolvedValue({
      signature: { valid: true, reason: "signature valid over canonical payload" },
      chain: { ok: true, checked: 2, first_break_seq: null, detail: null },
    });
    render(<ReceiptsPage />);

    const input = await screen.findByTestId("receipts-import-input");
    const envelope = { schema: "inspect_ia_agents-receipt-export-v1", receipts: [] };
    const file = new File([JSON.stringify(envelope)], "export.json", {
      type: "application/json",
    });
    fireEvent.change(input, { target: { files: [file] } });

    const verdict = await screen.findByTestId("receipts-import-verdict");
    expect(verdict).toHaveTextContent(/Signature\s+valide/);
    expect(verdict).toHaveTextContent(/Chaine\s+verifiee/);
    expect(vi.mocked(verifyImportedReceipts)).toHaveBeenCalledOnce();
  });

  it("shows an empty state when no side effect was traced", async () => {
    vi.mocked(getContextReceipts).mockResolvedValue({ receipts: [] });
    render(<ReceiptsPage />);
    expect(await screen.findByText(/Aucun recu/)).toBeInTheDocument();
  });

  it("surfaces a load error without crashing", async () => {
    vi.mocked(getContextReceipts).mockRejectedValue(new Error("receipts down"));
    render(<ReceiptsPage />);
    await waitFor(() => expect(screen.getByText(/receipts down/)).toBeInTheDocument());
  });
});
