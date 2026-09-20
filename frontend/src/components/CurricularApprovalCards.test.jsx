import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProposalCard } from "./CurricularApprovalCards";

afterEach(() => cleanup());

describe("tarjeta de propuesta técnica", () => {
      it("muestra nombre_curso sin exponer IDs de curso o sílabo", () => {
            render(
                  <ProposalCard
                        fila={{
                              id_pendiente: "PROP_TEC_CARD",
                              tipo: "competencia_tecnica",
                              nombre_competencia:
                                    "Diseñar arquitecturas de software",
                              nombre_curso: "Arquitectura de software",
                              id_curso: "CUR-TECH-1",
                              id_silabo: "SIL-TECH-1",
                              evidencia: ["Diseña arquitecturas de software."],
                        }}
                        onDecision={() => {}}
                  />,
            );

            const card = screen.getByTestId("curricular-proposal-card");
            expect(within(card).getByText("Curso")).toBeTruthy();
            expect(
                  within(card).getByText("Arquitectura de software"),
            ).toBeTruthy();
            expect(
                  within(card).queryByText("CUR-TECH-1", { exact: true }),
            ).toBeNull();
            expect(
                  within(card).queryByText("SIL-TECH-1", { exact: true }),
            ).toBeNull();
            expect(
                  within(card).getByText("PROP_TEC_CARD", { exact: true }),
            ).toBeTruthy();
      });
});
