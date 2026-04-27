import { beforeEach, describe, expect, it } from "vitest";
import { clearTokens, readTokens, writeTokens } from "./storage";

beforeEach(() => localStorage.clear());

describe("token storage", () => {
  it("returns null when nothing is stored", () => {
    expect(readTokens()).toBeNull();
  });

  it("round-trips a token pair", () => {
    writeTokens({ access: "a", refresh: "b" });
    expect(readTokens()).toEqual({ access: "a", refresh: "b" });
  });

  it("clears both tokens", () => {
    writeTokens({ access: "a", refresh: "b" });
    clearTokens();
    expect(readTokens()).toBeNull();
  });

  it("returns null when only one token is present", () => {
    localStorage.setItem("atp.access", "a");
    expect(readTokens()).toBeNull();
  });
});
