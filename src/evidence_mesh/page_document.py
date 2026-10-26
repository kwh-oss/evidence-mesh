"""Extract document text and provenance hints; HTML declarations are untrusted."""
from html.parser import HTMLParser
from datetime import date
import re
from .retrieval_profiles import research_reference


def clean_text(parts):
    return '\n'.join(s.strip() for s in ''.join(parts).splitlines() if s.strip())


class VisibleHTML(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}
    OMIT = {'script', 'style', 'noscript', 'template', 'nav', 'footer'}
    BLOCK = {'p', 'br', 'div', 'article', 'main', 'h1', 'h2', 'h3', 'li',
             'tr', 'blockquote', 'section'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title_parts, self.links = [], [], []
        self.stack, self.regions, self.metadata = [], [], []
        self.anchor_hints = []

    def _append(self, text):
        self.parts.append(text)
        for _, omitted, region in self.stack:
            if region is not None and not omitted:
                region['parts'].append(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        blocked = any(row[1] for row in self.stack)
        style = (attrs.get('style') or '').lower().replace(' ', '')
        omitted = (blocked or tag in self.OMIT or 'hidden' in attrs
                   or (attrs.get('aria-hidden') or '').lower() == 'true'
                   or 'display:none' in style or 'visibility:hidden' in style)
        in_head = any(row[0] == 'head' for row in self.stack)
        # Metadata is recorded as a page declaration, never used as proof.
        if tag == 'meta' and not blocked and len(self.metadata) < 16:
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            if key in {'article:published_time', 'date', 'pubdate', 'publishdate',
                       'datepublished', 'og:site_name', 'author'}:
                value = (attrs.get('content') or '').strip()[:300]
                if value:
                    self.metadata.append({'field': key, 'value': value,
                                          'basis': 'page-declared', 'verified': False})
        if tag == 'a' and not omitted and not in_head and attrs.get('href'):
            if len(self.links) < 100:
                self.links.append(attrs['href'])
                self.anchor_hints.append({'href': attrs['href'], 'parts': []})
        region = None
        classes = set((attrs.get('class') or '').lower().split())
        region_tag = tag if tag in {'article', 'main'} else (
            'cms-content' if classes & {'trs_ueditor', 'trs_editor'} else None)
        if region_tag and not omitted:
            region = {'tag': region_tag, 'parts': []}
            self.regions.append(region)
        if tag not in self.VOID:
            self.stack.append((tag, omitted, region))
        if tag in self.BLOCK and not omitted and not in_head:
            self._append('\n')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        index = next((i for i in range(len(self.stack) - 1, -1, -1)
                      if self.stack[i][0] == tag), None)
        if index is None:
            return
        if tag in self.BLOCK and not any(row[1] for row in self.stack):
            self._append('\n')
        del self.stack[index:]

    def handle_data(self, data):
        if any(row[1] for row in self.stack):
            return
        if any(row[0] == 'title' for row in self.stack):
            self.title_parts.append(data)
            return
        if not any(row[0] == 'head' for row in self.stack):
            self._append(data)
            if any(row[0] == 'a' for row in self.stack) and self.anchor_hints:
                self.anchor_hints[-1]['parts'].append(data)

    def source_link_hints(self):
        hints = []
        for anchor in self.anchor_hints:
            label = clean_text(anchor['parts'])[:200]
            if research_reference(anchor['href']) or any(cue in label.lower() for cue in (
                    '原文', '原始出处', '原始来源', '来源链接', 'original source',
                    '原始研究', '研究论文', 'original study', 'research paper')):
                hints.append({'href': anchor['href'], 'label': label,
                              'basis': 'page-declared-source-link', 'verified': False})
        return hints[:8]

    def document(self):
        # A semantic region is a heuristic, not a source authenticity verdict.
        for tag in ('article', 'cms-content', 'main'):
            candidates = [clean_text(r['parts']) for r in self.regions if r['tag'] == tag]
            candidates = [value for value in candidates if len(value) >= 40]
            if candidates:
                return max(candidates, key=len), 'semantic-' + tag
        return clean_text(self.parts), 'visible-text-fallback'

    def date_hints(self):
        hints = list(self.metadata)
        # Keep visible publication labels separate from hidden metadata. Neither
        # is authenticated; disagreement must not be silently resolved.
        visible = clean_text(self.parts)
        for value in re.findall(r'发布日期[：:]\s*(\d{4}-\d{1,2}-\d{1,2})', visible)[:3]:
            hints.append({'field': 'visible-publication-date', 'value': value,
                          'basis': 'page-visible-label', 'verified': False})
        document, method = self.document()
        if method != 'visible-text-fallback':
            # A standalone date near an article's end may be a sign-off date.
            # Keep it distinct from publication dates and from dates in prose.
            for line in document.splitlines()[-3:]:
                match = re.fullmatch(r'(\d{4})年(\d{1,2})月(\d{1,2})日', line.strip())
                if match:
                    try:
                        value = date(*map(int, match.groups())).isoformat()
                    except ValueError:
                        continue
                    hints.append({'field': 'visible-document-tail-date', 'value': value,
                                  'basis': 'page-visible-document-tail', 'verified': False,
                                  'meaning': 'unclassified-signoff-or-event-date'})
        return hints

    def date_conflict(self):
        values = set()
        for hint in self.date_hints():
            if hint['field'] in {'article:published_time', 'date', 'pubdate',
                                 'publishdate', 'datepublished', 'visible-publication-date'}:
                match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:$|[T ])', hint['value'])
                if match:
                    values.add(tuple(map(int, match.groups())))
        return len(values) > 1
