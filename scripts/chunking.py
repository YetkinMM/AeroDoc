"""Minimal normalization and token-bounded splitting with raw-character provenance."""

import hashlib
import json
import re
from dataclasses import dataclass


@dataclass
class Mapped:
    text: str
    origins: list  # One (block_key, raw_start, raw_end) or None per output character.

    def __post_init__(self):
        assert len(self.text)==len(self.origins)

    def cut(self,start,end):
        return Mapped(self.text[start:end],self.origins[start:end])

    def strip(self):
        start = len(self.text)-len(self.text.lstrip())
        end = len(self.text.rstrip())
        return self.cut(start,max(start,end))


def combine(items, separator="\n\n"):
    text, origins = [], []
    for item in items:
        if text:
            text.append(separator)
            origins.extend([None]*len(separator))
        text.append(item.text)
        origins.extend(item.origins)
    return Mapped("".join(text),origins)


HYPHEN = re.compile(r"([A-Za-z]+)-[ \t]*\r?\n[ \t]*([a-z]+)")
LIST_START = re.compile(r"(?:\d+[.)]|[•*‣▪-])\s")


def normalize(raw, key, start=0, evidence=None, preserve_lines=False):
    """Change whitespace only, plus provable line-end word joins. Never globally dehyphenate."""
    evidence = evidence or {}
    deletions, logs = {}, []
    for match in HYPHEN.finditer(raw):
        word = (match[1]+match[2]).lower()
        hyphen = match.start()+len(match[1])
        right = match.start(2)
        proof = evidence.get(word,[])
        status = "joined" if proof else "kept_ambiguous"
        logs.append({"operation":"line_end_hyphen","status":status,"block_key":key,
                     "raw_start":start+match.start(),"raw_end":start+match.end(),
                     "original":match.group(),"joined_word":match[1]+match[2],"support":proof})
        if proof:
            deletions[hyphen]=right
            logs[-1]["removed_raw_range"]=[start+hyphen,start+right]
    chars, origins, i = [], [], 0
    while i<len(raw):
        if i in deletions:
            i = deletions[i]
            continue
        if raw[i].isspace():
            end = i+1
            while end<len(raw) and raw[end].isspace():
                end+=1
            space = raw[i:end]
            next_line = raw[end:].split("\n",1)[0]
            if space.count("\n")>=2:
                output = "\n\n"
            elif "\n" in space and (preserve_lines or LIST_START.match(next_line)):
                output = "\n"
            else:
                output = " "
            chars.append(output)
            origins.extend([(key,start+i,start+end)]*len(output))
            i=end
        else:
            chars.append(raw[i])
            origins.append((key,start+i,start+i+1))
            i+=1
    result = Mapped("".join(chars),origins).strip()
    if result.text!=raw:
        logs.append({"operation":"whitespace_or_proven_word_join","block_key":key,
                     "raw_start":start,"raw_end":start+len(raw),"normalized_char_count":len(result.text)})
    return result,logs


def trace_spans(mapped, roles, sources):
    """Half-open offsets use Python Unicode code points, not bytes or tokenizer offsets."""
    spans = []
    for i,origin in enumerate(mapped.origins):
        if origin is None:
            continue
        key,start,end = origin
        role = roles[i]
        if spans and spans[-1]["block_key"]==key and spans[-1]["role"]==role and spans[-1]["chunk_end"]==i and (
                spans[-1]["raw_end"]==start or (spans[-1]["raw_start"]==start and spans[-1]["raw_end"]==end)):
            spans[-1]["raw_end"]=end
            spans[-1]["chunk_end"]=i+1
        else:
            source = sources[key]
            spans.append({"block_key":key,"pdf_page":source["pdf_page"],"printed_page":source["printed_page"],
                          "source_block_id":source["source_block_id"],"raw_start":start,"raw_end":end,
                          "chunk_start":i,"chunk_end":i+1,"role":role})
    return spans


class ModelTokenizer:
    def __init__(self,path):
        from tokenizers import Tokenizer
        self.tokenizer = Tokenizer.from_file(str(path))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def count(self,text,special=True):
        assert self.tokenizer.truncation is None
        return len(self.tokenizer.encode(text,add_special_tokens=special).ids)


def sentence_boundaries(text):
    result = []
    for m in re.finditer(r"[.!?][\"'’)]*(?=\s|$)",text):
        left = text[:m.end()]
        word = re.search(r"([\w.]+)[.!?][\"'’)]*$",left)
        if word and (word[1].isdigit() or word[1].lower() in ("mr","mrs","dr","e.g","i.e","u.s","fig")):
            continue
        result.append(m.end())
    return result


def split_group(mapped, tokenizer, target=400, maximum=500, overlap=32):
    """No text discarded; context overlap never leaves this caller-defined group."""
    text = mapped.text
    paragraphs = [m.start() for m in re.finditer(r"\n\n",text)]
    sentences = sentence_boundaries(text)
    chunks, forced = [], []
    start, previous_primary = 0, None
    while start<len(text):
        while start<len(text) and text[start].isspace():
            start+=1
        if start==len(text):
            break
        prefix = Mapped("",[])
        if previous_primary is not None and overlap:
            # Prefer complete trailing sentences; otherwise retain a word-aligned suffix.
            possible = sorted(set([0]+sentence_boundaries(previous_primary.text)+[
                m.end() for m in re.finditer(r"\s+",previous_primary.text)]))
            for position in possible:
                tail = previous_primary.cut(position,len(previous_primary.text)).strip()
                if tail.text and tokenizer.count(tail.text,special=False)<=overlap:
                    prefix=tail
                    break
        def render(end):
            primary = mapped.cut(start,end).strip()
            return combine([prefix,primary]) if prefix.text else primary
        if tokenizer.count(render(len(text)).text)<=target:
            end=len(text)
        else:
            choices = [end for end in paragraphs if end>start and tokenizer.count(render(end).text)<=target]
            # Do not emit a heading alone when a sentence fits in the same budget.
            substantive = [end for end in choices if len(text[start:end].split())>=20]
            if substantive:
                end=max(substantive)
            else:
                choices = [end for end in sentences if end>start and tokenizer.count(render(end).text)<=target]
                if choices:
                    end=max(choices)
                else:
                    lo,hi=start+1,len(text)
                    while lo<hi:
                        mid=(lo+hi+1)//2
                        if tokenizer.count(render(mid).text)<=maximum:
                            lo=mid
                        else:
                            hi=mid-1
                    end=lo
                    spaces=[m.start() for m in re.finditer(r"\s+",text[start:end])]
                    kind="forced_long_sentence_word_split"
                    if spaces:
                        end=start+spaces[-1]
                    else:
                        kind="forced_character_split"
                    if end<=start or tokenizer.count(render(end).text)>maximum:
                        raise ValueError("Cannot split within tokenizer budget without dropping text")
                    forced.append({"group_start":start,"group_end":end,"reason":kind})
        primary=mapped.cut(start,end).strip()
        final=combine([prefix,primary]) if prefix.text else primary
        if tokenizer.count(final.text)>maximum:
            raise ValueError("Final text exceeds hard token limit; truncation forbidden")
        roles = (["overlap"]*len(prefix.text)+["formatting"]*2+["primary"]*len(primary.text)) if prefix.text else ["primary"]*len(primary.text)
        chunks.append({"mapped":final,"roles":roles,"primary":primary,
                       "token_count":tokenizer.count(final.text),"overlap_token_count":tokenizer.count(prefix.text,False) if prefix.text else 0})
        previous_primary=primary
        start=end
    return chunks,forced


def stable_id(document_id,version,group_id,text,refs):
    payload=json.dumps([document_id,version,group_id,text,refs],ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return document_id+":chunk:"+hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
