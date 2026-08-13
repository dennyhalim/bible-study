/**
 * Minimal read-only D1 Worker example.
 * Bind the D1 database as `DB`.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/verse") {
      const book = url.searchParams.get("book");
      const chapter = Number(url.searchParams.get("chapter"));
      const verse = Number(url.searchParams.get("verse"));

      if (!book || !Number.isInteger(chapter) || !Number.isInteger(verse)) {
        return Response.json({ error: "Invalid verse reference" }, { status: 400 });
      }

      const row = await env.DB.prepare(`
        SELECT b.code, b.name, v.chapter, v.verse, v.text_kjv
        FROM verse v
        JOIN book b ON b.book_id = v.book_id
        WHERE b.code = ? AND v.chapter = ? AND v.verse = ?
      `).bind(book, chapter, verse).first();

      return Response.json(row ?? null);
    }

    return new Response("Bible Study API", {
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  },
};
