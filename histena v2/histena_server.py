import http.server
import socketserver
import json
import sqlite3
import urllib.parse
import dbAnnot
import os
import socket
import webbrowser
import re

# --- Tag-based annotation helpers ---
def get_raw_pos(raw, rendered_pos):
    """Map rendered char index to raw text index (skip over <n{id}> tags)"""
    count = 0; i = 0
    while i < len(raw):
        m = re.match(r'</?n\d+>', raw[i:])
        if m: i += len(m.group()); continue
        if count == rendered_pos: return i
        count += 1; i += 1
    return len(raw)

def insert_tag(raw, aid, rb, re_pos):
    """Insert EXACTLY ONE <n{aid}> and ONE </n{aid}> tag around the rendered text range [rb:re_pos]"""
    # 1. Clean up ALL existing tags of THIS specific annotation first
    text_clean_of_aid = remove_tag(raw, aid)
    
    # 2. Find where the start (rb) and end (re_pos) lie in the text
    # that may contain OTHER tags (<n84>, <n85>, etc.)
    # get_raw_pos correctly skips existing tags to find the visual position.
    raw_start = get_raw_pos(text_clean_of_aid, rb)
    raw_end = get_raw_pos(text_clean_of_aid, re_pos)
    
    # 3. Construct the new raw text with exactly one pair of tags
    return text_clean_of_aid[:raw_start] + f'<n{aid}>' + text_clean_of_aid[raw_start:raw_end] + f'</n{aid}>' + text_clean_of_aid[raw_end:]

def remove_tag(raw, aid):
    """Remove <n{aid}> and </n{aid}> tags, keeping inner text"""
    raw = re.sub(f'<n{aid}>', '', raw or '')
    raw = re.sub(f'</n{aid}>', '', raw)
    return raw

def export_to_json():
    """Export all database tables to a unified JSON file for easy consultation"""
    try:
        data = {
            "works": [],
            "docs": [],
            "persons": [],
            "locations": [],
            "keywords": [],
            "annotations": []
        }
        
        # Works
        rows = dbAnnot.fetch_all("SELECT ID, title, description, abbreviation FROM works")
        data["works"] = [{"id": r[0], "title": r[1], "description": r[2], "abbrev": r[3]} for r in rows]
        
        # Docs
        rows = dbAnnot.fetch_all("SELECT ID, id_work, title, date, text, ref, id_location, id_author FROM docs")
        data["docs"] = [{"id": r[0], "work_id": r[1], "title": r[2], "date": r[3], "text": r[4], "ref": r[5], "loc_id": r[6], "auth_id": r[7]} for r in rows]
        
        # Persons
        rows = dbAnnot.fetch_all("SELECT ID, name, info FROM persons")
        data["persons"] = [{"id": r[0], "name": r[1], "info": r[2]} for r in rows]
        
        # Locations
        rows = dbAnnot.fetch_all("SELECT ID, name, country, lat, long, geonameId FROM locations")
        data["locations"] = [{"id": r[0], "name": r[1], "country": r[2], "lat": r[3], "lon": r[4], "geonameId": r[5]} for r in rows]
        
        # Keywords
        rows = dbAnnot.fetch_all("SELECT ID, name, description FROM keywords")
        data["keywords"] = [{"id": r[0], "name": r[1], "description": r[2]} for r in rows]
        
        # Annotations (with relations)
        rows = dbAnnot.fetch_all("SELECT ID, type, begin, end, id_doc FROM annotations")
        for r in rows:
            aid, atype, abegin, aend, adid = r
            annot = {"id": aid, "type": atype, "begin": abegin, "end": aend, "doc_id": adid, "entity_id": None}
            
            # Find linked entity
            if atype == 'person':
                er = dbAnnot.fetch_one("SELECT id_person FROM annotationPerson WHERE id_annotation=?", (aid,))
                if er: annot["entity_id"] = er[0]
            elif atype == 'location':
                er = dbAnnot.fetch_one("SELECT id_location FROM annotationLocation WHERE id_annotation=?", (aid,))
                if er: annot["entity_id"] = er[0]
            elif atype == 'keyword':
                er = dbAnnot.fetch_one("SELECT id_keyword FROM annotationKeyword WHERE id_annotation=?", (aid,))
                if er: annot["entity_id"] = er[0]
            
            data["annotations"].append(annot)
            
        json_filename = dbAnnot.current_db_path.replace('.db', '.json')
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Project exported to {json_filename}")
    except Exception as e:
        print(f"Error during JSON export: {e}")

def parse_annots_from_text(text, doc_id):
    """Return annotation metadataUnique to this text"""
    ids = set(int(x) for x in re.findall(r'<n(\d+)>', text or ''))
    result = []
    for aid in ids:
        row = dbAnnot.fetch_one("SELECT type FROM annotations WHERE id=?", (aid,))
        if row: result.append({"id": aid, "type": row[0]})
    return result

class HistenaAPIHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url.query)
        
        if url.path == "/api/works":
            res = dbAnnot.fetch_all("SELECT * FROM works ORDER BY title")
            data = [{"id": r[0], "title": r[1], "abbrev": r[3], "desc": r[2]} for r in res]
            self.send_json(data)
        
        elif url.path == "/api/docs":
            wid = params.get('work_id', [0])[0]
            res = dbAnnot.fetch_all("SELECT id, title, date FROM docs WHERE id_work=? ORDER BY date", (wid,))
            data = [{"id": r[0], "title": r[1], "date": r[2]} for r in res]
            self.send_json(data)
            
        elif url.path == "/api/doc":
            did = params.get('doc_id', [0])[0]
            doc = dbAnnot.fetch_one("SELECT * FROM docs WHERE id=?", (did,))
            if doc:
                text = doc[4] or ""
                annots = parse_annots_from_text(text, did)
                data = {
                    "id": doc[0], "work_id": doc[1],
                    "title": doc[2], "date": doc[3], "text": text, "ref": doc[5],
                    "loc_id": doc[6], "auth_id": doc[7],
                    "annotations": annots
                }
                self.send_json(data)
            else: self.send_error(404)

        elif url.path == "/api/entity_info":
            aid = params.get('id', [0])[0]
            atype = params.get('type', [""])[0]
            info = {}
            if atype == 'person':
                r = dbAnnot.fetch_one("SELECT p.name, p.info FROM annotationPerson ap JOIN persons p ON ap.id_person = p.id WHERE ap.id_annotation=?", (aid,))
                if r: info = {"name": r[0], "details": r[1]}
            elif atype == 'location':
                r = dbAnnot.fetch_one("SELECT l.name, l.country, l.lat, l.long FROM annotationLocation al JOIN locations l ON al.id_location = l.id WHERE al.id_annotation=?", (aid,))
                if r: info = {"name": r[0], "details": f"{r[1]} [{r[2]}/{r[3]}]"}
            elif atype == 'keyword':
                r = dbAnnot.fetch_one("SELECT k.name, k.description FROM annotationKeyword ak JOIN keywords k ON ak.id_keyword = k.id WHERE ak.id_annotation=?", (aid,))
                if r: info = {"name": r[0], "details": r[1]}
            self.send_json(info)

        elif url.path == "/api/entity_raw":
            aid = params.get('id', [0])[0]
            atype = params.get('type', [""])[0]
            info = {}
            if atype == 'person':
                r = dbAnnot.fetch_one("SELECT p.id, p.name, p.info FROM annotationPerson ap JOIN persons p ON ap.id_person = p.id WHERE ap.id_annotation=?", (aid,))
                if r: info = {"id": r[0], "name": r[1], "info": r[2]}
            elif atype == 'location':
                r = dbAnnot.fetch_one("SELECT l.id, l.name, l.country, l.lat, l.long FROM annotationLocation al JOIN locations l ON al.id_location = l.id WHERE al.id_annotation=?", (aid,))
                if r: info = {"id": r[0], "name": r[1], "country": r[2], "lat": r[3], "lon": r[4]}
            elif atype == 'keyword':
                r = dbAnnot.fetch_one("SELECT k.id, k.name, k.description FROM annotationKeyword ak JOIN keywords k ON ak.id_keyword = k.id WHERE ak.id_annotation=?", (aid,))
                if r: info = {"id": r[0], "name": r[1], "description": r[2]}
            self.send_json(info)

        elif url.path == "/api/search_entities":
            etype = params.get('type', ['person'])[0]
            query = params.get('q', [''])[0]
            if etype == 'doc':
                res = dbAnnot.fetch_all("SELECT id, title FROM docs WHERE title LIKE ? LIMIT 10", (f"%{query}%",))
                data = [{"id": r[0], "name": r[1]} for r in res]
            else:
                table = {'person': 'persons', 'location': 'locations', 'keyword': 'keywords', 'work': 'works'}[etype]
                col = 'title' if etype == 'work' else 'name'
                res = dbAnnot.fetch_all(f"SELECT id, {col} FROM {table} WHERE {col} LIKE ? LIMIT 10", (f"%{query}%",))
                data = [{"id": r[0], "name": r[1]} for r in res]
            self.send_json(data)

        elif url.path == "/api/stats":
            stats = {
                "docs": dbAnnot.fetch_one("SELECT count(*) FROM docs")[0],
                "persons": dbAnnot.fetch_one("SELECT count(*) FROM persons")[0],
                "locations": dbAnnot.fetch_one("SELECT count(*) FROM locations")[0],
                "keywords": dbAnnot.fetch_one("SELECT count(*) FROM keywords")[0],
                "annots": dbAnnot.fetch_one("SELECT count(*) FROM annotations")[0],
                "annots_person": dbAnnot.fetch_one("SELECT count(*) FROM annotations WHERE type='person'")[0],
                "annots_location": dbAnnot.fetch_one("SELECT count(*) FROM annotations WHERE type='location'")[0],
                "annots_keyword": dbAnnot.fetch_one("SELECT count(*) FROM annotations WHERE type='keyword'")[0]
            }
            self.send_json(stats)

        elif url.path == "/api/projects":
            dbs = [f for f in os.listdir('.') if f.endswith('.db')]
            self.send_json({"projects": dbs, "current": dbAnnot.current_db_path})

        else:
            return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(length).decode('utf-8'))

        if url.path == "/api/switch_project":
            dbAnnot.init(body['name'])
            export_to_json()
            self.send_json({"status": "ok"})

        elif url.path == "/api/new_project":
            try:
                path = dbAnnot.create_new(body['name'])
                dbAnnot.init(path)
                export_to_json()
                self.send_json({"status": "ok", "path": path})
            except Exception as e:
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/new_work":
            try:
                dbAnnot.execute("INSERT INTO works (title, abbreviation, description) VALUES (?,?,?)", 
                                (body.get('title'), body.get('abbrev'), body.get('description')))
                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok", "id": dbAnnot.last_id()})
            except Exception as e:
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/save_doc":
            try:
                did = body.get('id')
                new_text = body['text']  # May contain <n{id}> tags (inline edit) or be plain (new doc)

                if did:
                    # Inline edit: text has <n{}> tags. Sync: remove annotations no longer in text.
                    old_aids = set(int(x) for x in re.findall(r'<n(\d+)>', dbAnnot.fetch_one("SELECT text FROM docs WHERE id=?", (did,))[0] or ''))
                    new_aids = set(int(x) for x in re.findall(r'<n(\d+)>', new_text))
                    removed = old_aids - new_aids
                    for aid in removed:
                        dbAnnot.execute("DELETE FROM annotationPerson WHERE id_annotation=?", (aid,))
                        dbAnnot.execute("DELETE FROM annotationLocation WHERE id_annotation=?", (aid,))
                        dbAnnot.execute("DELETE FROM annotationKeyword WHERE id_annotation=?", (aid,))
                        dbAnnot.execute("DELETE FROM annotations WHERE id=?", (aid,))
                    sql = "UPDATE docs SET title=?, date=?, text=?, ref=?, id_location=?, id_author=? WHERE id=?"
                    params = (body.get('title', ''), body.get('date', ''), new_text, body.get('ref', ''), body.get('loc_id'), body.get('auth_id'), did)
                    dbAnnot.execute(sql, params)
                else:
                    sql = "INSERT INTO docs (id_work, title, date, text, ref, id_location, id_author) VALUES (?,?,?,?,?,?,?)"
                    params = (body['work_id'], body['title'], body.get('date', ''), new_text, body.get('ref', ''), body.get('loc_id'), body.get('auth_id'))
                    dbAnnot.execute(sql, params)
                    did = dbAnnot.last_id()

                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok", "id": did})
            except Exception as e:
                print(f"Error in save_doc: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)
            
        elif url.path == "/api/delete_doc":
            try:
                did = body['doc_id']
                dbAnnot.execute("DELETE FROM annotationPerson WHERE id_annotation IN (SELECT id FROM annotations WHERE id_doc=?)", (did,))
                dbAnnot.execute("DELETE FROM annotationLocation WHERE id_annotation IN (SELECT id FROM annotations WHERE id_doc=?)", (did,))
                dbAnnot.execute("DELETE FROM annotationKeyword WHERE id_annotation IN (SELECT id FROM annotations WHERE id_doc=?)", (did,))
                dbAnnot.execute("DELETE FROM annotations WHERE id_doc=?", (did,))
                dbAnnot.execute("DELETE FROM docs WHERE id=?", (did,))
                dbAnnot.commit()
                self.send_json({"status": "ok"})
            except Exception as e:
                print(f"Error in delete_doc: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/annotate":
            try:
                doc_id = body['doc_id']
                etype = body['type']
                entity_id = body['entity_id']
                r_begin = int(str(body['begin']).split('.')[-1])
                r_end = int(str(body['end']).split('.')[-1])

                # Create annotation record
                dbAnnot.execute("INSERT INTO annotations (type, begin, end, id_doc) VALUES (?,?,?,?)",
                                (etype, f'1.{r_begin}', f'1.{r_end}', doc_id))
                aid = dbAnnot.last_id()
                table_map = {'person': ('annotationPerson', 'id_person'),
                             'location': ('annotationLocation', 'id_location'),
                             'keyword': ('annotationKeyword', 'id_keyword')}
                tbl, col = table_map[etype]
                dbAnnot.execute(f"INSERT INTO {tbl} (id_annotation, {col}) VALUES (?,?)", (aid, entity_id))

                # Insert <n{aid}> tag into document text
                doc_text = dbAnnot.fetch_one("SELECT text FROM docs WHERE id=?", (doc_id,))[0] or ''
                new_text = insert_tag(doc_text, aid, r_begin, r_end)
                dbAnnot.execute("UPDATE docs SET text=? WHERE id=?", (new_text, doc_id))

                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok", "id": aid})
            except Exception as e:
                print(f"Error in annotate: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/save_entity":
            try:
                entity_type = body['type']
                data = body['data']
                eid = body.get('id')
                
                if entity_type == 'person':
                    if eid:
                        dbAnnot.execute("UPDATE persons SET name=?, info=? WHERE ID=?", (data.get('name'), data.get('info'), eid))
                    else:
                        dbAnnot.execute("INSERT INTO persons (name, info) VALUES (?,?)", (data.get('name'), data.get('info')))
                        eid = dbAnnot.last_id()
                elif entity_type == 'keyword':
                    # The actual database column is 'description', NOT 'definition'
                    desc = data.get('description') or data.get('definition') or ''
                    if eid:
                        dbAnnot.execute("UPDATE keywords SET name=?, description=? WHERE ID=?", (data.get('name'), desc, eid))
                    else:
                        dbAnnot.execute("INSERT INTO keywords (name, description) VALUES (?,?)", (data.get('name'), desc))
                        eid = dbAnnot.last_id()
                elif entity_type == 'location':
                    # The actual database columns are 'lat', 'long', NOT 'latitude', 'longitude'
                    lat = data.get('lat') or data.get('latitude')
                    lon = data.get('long') or data.get('longitude')
                    if eid:
                        dbAnnot.execute("UPDATE locations SET name=?, country=?, lat=?, long=? WHERE ID=?", 
                                        (data.get('name'), data.get('country'), lat, lon, eid))
                    else:
                        dbAnnot.execute("INSERT INTO locations (name, country, lat, long) VALUES (?,?,?,?)", 
                                        (data.get('name'), data.get('country'), lat, lon))
                        eid = dbAnnot.last_id()
                
                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok", "id": eid})
            except Exception as e:
                print(f"Error in save_entity: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/delete_annotation":
            try:
                aid = body['id']
                doc_id = body['doc_id']
                # Remove tag from text
                doc_text = dbAnnot.fetch_one("SELECT text FROM docs WHERE id=?", (doc_id,))[0] or ''
                new_text = remove_tag(doc_text, aid)
                dbAnnot.execute("UPDATE docs SET text=? WHERE id=?", (new_text, doc_id))
                # Remove from tables
                dbAnnot.execute("DELETE FROM annotationPerson WHERE id_annotation=?", (aid,))
                dbAnnot.execute("DELETE FROM annotationLocation WHERE id_annotation=?", (aid,))
                dbAnnot.execute("DELETE FROM annotationKeyword WHERE id_annotation=?", (aid,))
                dbAnnot.execute("DELETE FROM annotations WHERE id=?", (aid,))
                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok"})
            except Exception as e:
                print(f"Error in delete_annotation: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)

        elif url.path == "/api/update_annotation_position":
            try:
                aid = body['id']
                r_begin = int(str(body['begin']).split('.')[-1])
                r_end = int(str(body['end']).split('.')[-1])
                
                # Fetch doc_id for this annotation
                doc_id_row = dbAnnot.fetch_one("SELECT id_doc FROM annotations WHERE id=?", (aid,))
                if not doc_id_row:
                    self.send_json({"status": "error", "error": "Annotation not found"}, 404)
                    return
                doc_id = doc_id_row[0]

                # Update annotations table
                dbAnnot.execute("UPDATE annotations SET begin=?, end=? WHERE id=?", 
                                (f'1.{r_begin}', f'1.{r_end}', aid))

                # Update text tags
                doc_text = dbAnnot.fetch_one("SELECT text FROM docs WHERE id=?", (doc_id,))[0] or ''
                
                # Remove tag first
                doc_text = remove_tag(doc_text, aid)
                
                # Insert tag at new position
                new_text = insert_tag(doc_text, aid, r_begin, r_end)
                
                dbAnnot.execute("UPDATE docs SET text=? WHERE id=?", (new_text, doc_id))
                dbAnnot.commit()
                export_to_json()
                self.send_json({"status": "ok"})
            except Exception as e:
                print(f"Error in update_annotation_position: {e}")
                self.send_json({"status": "error", "error": str(e)}, 500)

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

if __name__ == "__main__":
    dbAnnot.init()
    export_to_json()
    PORT = 8000
    
    import socket
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", PORT), HistenaAPIHandler) as httpd:
            print(f"Histena running at http://localhost:{PORT}")
            webbrowser.open(f"http://localhost:{PORT}")
            httpd.serve_forever()
    except OSError:
        print(f"ERROR: El port {PORT} ja està ocupat. Si el servidor ja s'està executant, pots anar a http://localhost:{PORT}")
