export class ScenaraError extends Error {
    code;
    details;
    constructor(code, message, details) {
        super(message);
        this.code = code;
        this.details = details;
        this.name = "ScenaraError";
    }
}
//# sourceMappingURL=client_types.js.map