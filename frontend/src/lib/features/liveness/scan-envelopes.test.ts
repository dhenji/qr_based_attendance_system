import { describe, it, expect } from "vitest";
import { parseError } from "$lib/api/client";
import { toScanMessage, SCAN_ERROR_MESSAGES } from "./errors";

function resp(
  status: number,
  body: unknown,
  contentType = "application/json",
): Response {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { "content-type": contentType },
  });
}

describe("scan error envelopes -> toScanMessage", () => {
  const fallback = "fallback message";

  it("AppException envelope unwraps code/message/status", async () => {
    const r = resp(400, {
      detail: { code: "duplicate_scan", message: "dup", field: "x" },
    });
    const err = await parseError(r);
    expect(err.code).toBe("duplicate_scan");
    expect(err.status).toBe(400);
    expect(toScanMessage(err, fallback)).toContain("already been recorded");
  });

  it("attempt exhaustion envelope defaults to 0 attempts remaining", async () => {
    const r = resp(409, {
      detail: {
        code: "attendance_attempt_limit_reached",
        message:
          "Maximum of 3 attendance attempts reached for this session (0 attempts remaining)",
      },
    });
    const err = await parseError(r);
    expect(err.code).toBe("attendance_attempt_limit_reached");
    expect(err.status).toBe(409);
    expect(toScanMessage(err, fallback)).toBe(
      `${SCAN_ERROR_MESSAGES.attendance_attempt_limit_reached} (0 attempts remaining)`,
    );
  });

  it("FastAPI 422 list becomes validation_error", async () => {
    const r = resp(422, {
      detail: [
        {
          loc: ["body", "student_number"],
          msg: "field required",
          type: "value_error.missing",
        },
      ],
    });
    const err = await parseError(r);
    expect(err.code).toBe("validation_error");
    expect(err.status).toBe(422);
    expect(err.field).toBe("student_number");
    expect(toScanMessage(err, fallback)).toBe("field required");
  });

  it("plain-string 401 becomes invalid_token", async () => {
    const r = resp(401, { detail: "Not authenticated" });
    const err = await parseError(r);
    expect(err.code).toBe("invalid_token");
    expect(err.status).toBe(401);
    expect(toScanMessage(err, fallback)).toContain("login session has expired");
  });

  it("plain-string 403 becomes forbidden", async () => {
    const r = resp(403, { detail: "Forbidden" });
    const err = await parseError(r);
    expect(err.code).toBe("forbidden");
    expect(err.status).toBe(403);
  });

  it("410 with unknown code -> closed copy", async () => {
    const r = resp(410, { detail: { code: "gone", message: "gone" } });
    const err = await parseError(r);
    expect(toScanMessage(err, fallback)).toBe(
      "This session has closed for scanning.",
    );
  });

  it("plain-text 500 preserves snippet", async () => {
    const r = resp(500, "Internal Server Error", "text/plain");
    const err = await parseError(r);
    expect(err.code).toBe("request_failed");
    expect(err.message).toContain("Internal Server Error");
  });
});
