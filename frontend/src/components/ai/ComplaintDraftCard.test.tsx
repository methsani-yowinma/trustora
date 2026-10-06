import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { renderWithIntl } from "@/test/render";

import { ComplaintDraftCard } from "./ComplaintDraftCard";

const clientApi = vi.fn();
vi.mock("@/lib/api/browser", () => ({ clientApi: (...args: unknown[]) => clientApi(...args) }));

const draft = {
  order_id: "20000000-0000-4000-8000-000000000001",
  order_number: "TR-AB12CD34",
  category: "DELIVERY",
  description: "My order has not arrived yet.",
};

describe("ComplaintDraftCard", () => {
  beforeEach(() => {
    clientApi.mockReset();
  });

  it("says nothing has been submitted and pre-fills the draft", () => {
    renderWithIntl(<ComplaintDraftCard draft={draft} />);
    expect(screen.getByText("Complaint draft (not submitted)")).toBeTruthy();
    expect((screen.getByLabelText("Description") as HTMLTextAreaElement).value).toBe(draft.description);
    expect((screen.getByLabelText("Category") as HTMLSelectElement).value).toBe("DELIVERY");
    expect(clientApi).not.toHaveBeenCalled();
  });

  it("submits the (edited) draft through the normal complaints endpoint", async () => {
    clientApi.mockResolvedValue({ id: "c1" });
    const user = userEvent.setup();
    renderWithIntl(<ComplaintDraftCard draft={draft} />);

    await user.selectOptions(screen.getByLabelText("Category"), "WRONG_PRODUCT");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "I received a different saree.");
    await user.click(screen.getByRole("button", { name: "Submit complaint" }));

    await waitFor(() => expect(screen.getByText(/Complaint submitted/)).toBeTruthy());
    const [path, options] = clientApi.mock.calls[0];
    expect(path).toBe(`/orders/${draft.order_id}/complaints`);
    expect(options.method).toBe("POST");
    expect(options.body.get("category")).toBe("WRONG_PRODUCT");
    expect(options.body.get("description")).toBe("I received a different saree.");
    expect(screen.getByRole("link", { name: "View order" }).getAttribute("href")).toBe(`/orders/${draft.order_id}`);
  });

  it("cannot be submitted with a too-short description", async () => {
    const user = userEvent.setup();
    renderWithIntl(<ComplaintDraftCard draft={draft} />);
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "late");
    expect(screen.getByText("Please describe the problem in at least 10 characters.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Submit complaint" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("can be discarded without sending anything", async () => {
    const user = userEvent.setup();
    renderWithIntl(<ComplaintDraftCard draft={draft} />);
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.getByText("Draft discarded. Nothing was submitted.")).toBeTruthy();
    expect(clientApi).not.toHaveBeenCalled();
  });

  it("shows API errors in the user's language", async () => {
    clientApi.mockImplementation(async () => {
      throw new ApiError(409, "complaint_open", "open");
    });
    const user = userEvent.setup();
    renderWithIntl(<ComplaintDraftCard draft={draft} />, "si");
    await user.click(screen.getByRole("button", { name: "පැමිණිල්ල ඉදිරිපත් කරන්න" }));
    await waitFor(() => expect(screen.getByText("මෙම ඇණවුමට දැනටමත් විවෘත පැමිණිල්ලක් ඇත.")).toBeTruthy());
  });
});
