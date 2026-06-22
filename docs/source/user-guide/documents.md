# Documents

Documents are the evidence base for generation.

## Supported Documents

The backend contains loaders for common technical document formats:

- PDF;
- DOCX;
- Markdown;
- spreadsheet-oriented content where configured.

## Upload Behavior

When a document is uploaded, the system:

1. stores the original file;
2. extracts text;
3. splits the text into chunks;
4. stores chunk metadata;
5. embeds chunks for retrieval when semantic memory is enabled;
6. makes the chunks available to the AI pipeline.

## Good Project Documents

Good input documents contain:

- explicit requirement IDs;
- normative language such as "shall";
- acceptance criteria;
- architecture notes;
- interfaces and APIs;
- constraints;
- known incidents or risks.

## Bad Project Documents

The system will struggle with:

- scanned documents without OCR;
- screenshots instead of text;
- vague documents with no requirements;
- very large files with repeated boilerplate;
- documents with conflicting requirement IDs.
