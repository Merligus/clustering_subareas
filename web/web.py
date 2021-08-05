# run in clustering_subareas "python -m web.web"
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from algoritmos.smacof import MDS
from .data import Params, Data
import os
from algoritmos.finder import ClusterFinder
from flask import Flask, redirect, url_for, render_template, request, session

app = Flask(__name__)
app.secret_key = "key para session"
db = Data("_2010_only_journals", "union", "./data")

@app.route("/", methods=["POST", "GET"])
@app.route("/search", methods=["POST", "GET"])
def search():
    if request.method == "POST" and "list" in request.form:
        venues_s = set(request.form["list"].strip().split())

        if len(venues_s) == 0:
            print(f"Nenhuma venue passada")
            return render_template("search_venues.html")

        global db
        in_set_conf = set()
        s = ''
        for key in db.index_to_journalname:
            if db.index_to_journalname[key] in venues_s:
                in_set_conf.add(key)
                s += db.index_to_journalname[key] + ' '

        if len(s) == 0:
            print(f"Nenhum identificado")
            return render_template("search_venues.html")

        parsed = Params(request.form["in_name"], 'union', './data', request.form["function"], len(db.distance))
        
        parsed.old_cluster = in_set_conf
        parsed.cf = ClusterFinder(db.children[request.form["function"]], len(db.distance), in_set_conf, [])
        c, parsed.iteration = parsed.cf.find_cluster(0)
        if parsed.iteration == len(parsed.cf.children):
            print(f"Nenhum cluster achado")
            return render_template("search_venues.html")

        parsed.cluster = parsed.cf.labels_sets[c]
        
        session["mode"] = "union"
        session["in_name"] = request.form["in_name"]
        session["function"] = request.form["function"]
        session["old_cluster"] = list(parsed.old_cluster)
        session["cluster"] = list(parsed.cluster)
        session["iteration"] = parsed.iteration
        session["in_set_conf"] = list(in_set_conf)

        return redirect(url_for("listar_conferencias", next="0"))
    else:
        return render_template("search_venues.html")

@app.route("/venues<next>", methods=["POST", "GET"])
def listar_conferencias(next):
    if "cluster" not in session:
        return redirect(url_for("search"))
        
    global db
    parsed = Params(session["in_name"], session["mode"], './data', session["function"], len(db.distance), session["iteration"], 
                    db.children[session["function"]], session["old_cluster"], session["cluster"], session["in_set_conf"])
    if request.method == "POST" or next == "1":
        parsed.old_cluster = parsed.cluster
        c, parsed.iteration = parsed.cf.find_cluster(parsed.iteration+1)
        if parsed.iteration < len(parsed.cf.children):
            parsed.cluster = parsed.cf.labels_sets[c]

        session["old_cluster"] = list(parsed.old_cluster)
        session["cluster"] = list(parsed.cluster)
        session["iteration"] = parsed.iteration
            
    i = 0
    old_cluster_l = []
    for vi in parsed.old_cluster:
        old_cluster_l.append((i, db.index_to_journal_complete_name[vi]))
        i += 1

    new_cluster = []
    for vi in parsed.cluster:
        if vi not in parsed.old_cluster:
            new_cluster.append((i, db.index_to_journal_complete_name[vi]))
            i += 1

    return render_template("show_venues.html", new=new_cluster, old=old_cluster_l, tam_l=len(parsed.cluster))

@app.route("/frequency")
def listar_frequencia():
    if "cluster" not in session:
        return redirect(url_for("search"))

    global db
    parsed = Params(session["in_name"], session["mode"], './data', session["function"], len(db.distance), session["iteration"], 
                    db.children[session["function"]], session["old_cluster"], session["cluster"], session["in_set_conf"])
    
    sentences = []
    for vi in parsed.cluster:
        sentences.append(db.index_to_journal_complete_name[vi].lower())
    lista = parsed.cf.show_top(sentences, n=10)

    return render_template("show_frequency.html", word_freq=lista)

@app.route("/graph")
def show_graph():
    if "cluster" not in session:
        return redirect(url_for("search"))

    if len(session["cluster"]) <= 2 or len(session["cluster"]) >= 15:
        return redirect(url_for("listar_conferencias", next="0"))

    global db
    parsed = Params(session["in_name"], session["mode"], './data', session["function"], len(db.distance), session["iteration"], 
                    db.children[session["function"]], session["old_cluster"], session["cluster"], session["in_set_conf"])
    
    g = nx.Graph()

    vertices = []
    for vi in parsed.cluster:
        vertices.append(vi)

    distance_temp = np.zeros((len(parsed.cluster), len(parsed.cluster)))
    m = MDS(ndim=2, weight_option="d-2", itmax=10000)

    journalname = {}
    node_size = []
    v1 = 0
    while v1 < len(parsed.cluster):
        v2 = v1 + 1
        while v2 < len(parsed.cluster):
            if db.distance[vertices[v1], vertices[v2]] > 0 and db.distance[vertices[v1], vertices[v2]] < np.inf:
                if db.adj_mat[vertices[v1], vertices[v2]] > 0:
                    g.add_edge(v1, v2, weight=db.adj_mat[vertices[v1], vertices[v2]])
                distance_temp[v1, v2] = distance_temp[v2, v1] = db.distance[vertices[v1], vertices[v2]]
            v2 += 1
        journalname[v1] = db.index_to_journalname[vertices[v1]]
        node_size.append(4*np.ceil(db.nauthors[vertices[v1]]/len(parsed.cluster)))
        v1 += 1

    mds_model = m.fit(distance_temp) # shape = journals x n_components
    X_transformed = mds_model['conf']

    width = nx.get_edge_attributes(g, 'weight')
    min_w = min(width.values())
    max_w = max(width.values())
    for w in width:
        width[w] = 0.5 + 4*(width[w] - min_w)/(max_w - min_w)

    edge_labels = {}
    for v1, v2, w in g.edges.data():
        edge_labels[(v1, v2)] = f"{db.adj_mat[vertices[v1], vertices[v2]]:.2f}" # w['weight']
        # print(f'{v1}:{journalname[v1]}:{nauthors[v1]}, {v2}:{journalname[v2]}:{nauthors[v2]} = {distance[vertices[v1], vertices[v2]]}:{w["weight"]}')

    fig = plt.figure(figsize=(24,24))
    ax = fig.add_axes([0,0,1,1])
    # pos = nx.spring_layout(g)
    pos = {}
    for vi in range(len(parsed.cluster)):
        pos[vi] = X_transformed[vi]
    # print(pos)
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=node_size, node_color="#A8C1FB")
    nx.draw_networkx_labels(g, pos, ax=ax, labels=journalname, font_color="#DF0000", font_size=22)
    nx.draw_networkx_edges(g, pos, ax=ax, width=list(width.values()))
    nx.draw_networkx_edge_labels(g, pos, ax=ax, edge_labels=edge_labels, font_size=18)
    filename = f"graph{np.random.random()}.png"
    for file in os.listdir("./web/static/images/"):
        os.remove("./web/static/images/" + file)
    plt.savefig(f'./web/static/images/{filename}')

    del journalname
    del vertices
    del g

    # setting the list
    i = 0
    old_cluster_l = []
    for vi in parsed.old_cluster:
        old_cluster_l.append((i, db.index_to_journal_complete_name[vi]))
        i += 1

    new_cluster = []
    for vi in parsed.cluster:
        if vi not in parsed.old_cluster:
            new_cluster.append((i, db.index_to_journal_complete_name[vi]))
            i += 1
        
    return render_template("show_graph.html", src=filename, new=new_cluster, old=old_cluster_l, tam_l=len(parsed.cluster))

def run():
    app.run(debug=False)

# run()