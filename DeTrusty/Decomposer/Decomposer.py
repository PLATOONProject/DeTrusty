__author__ = 'Kemele M. Endris'

import logging

import DeTrusty.Decomposer.utils as utils
from DeTrusty.Sparql.Parser import queryParser
from DeTrusty.Sparql.Parser.services import Service, Triple, Filter, Optional, UnionBlock, JoinBlock
from DeTrusty.Decomposer import Tree

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('.decompositions.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class Decomposer(object):

    def __init__(self, query, config, tempType="MULDER", joinstarslocally=True):
        self.tempType = tempType
        self.query = queryParser.parse(query)
        self.prefixes = utils.getPrefs(self.query.prefs)
        self.config = config
        self.joinlocally = joinstarslocally

    def decompose(self):
        groups = self.decomposeUnionBlock(self.query.body)
        if groups is None:
            return None
        if groups == []:
            return None
        self.query.body = groups
        logger.info('Decomposition obtained')
        logger.info(self.query)

        if self.query is None:
            return None

        self.query.body = self.makePlanQuery(self.query)

        return self.query

    def decomposeUnionBlock(self, ub):
        r = []
        filters = []
        for jb in ub.triples:
            pjb = self.decomposeJoinBlock(jb)
            if pjb:
                r.append(pjb)
                filters.extend(pjb.filters)
        if r:
            return UnionBlock(r)
        else:
            return None

    def decomposeJoinBlock(self, jb):
        tl = []
        sl = []
        fl = []
        for bgp in jb.triples:
            if isinstance(bgp, Triple):
                tl.append(bgp)
            elif isinstance(bgp, Filter):
                fl.append(bgp)
            elif isinstance(bgp, Optional):
                ubb = self.decomposeUnionBlock(bgp.bgg)
                skipp = False
                for ot in ubb.triples:
                    if isinstance(ot, JoinBlock) and len(ot.triples) > 1 and len(ot.filters) > 0:
                        skipp = True
                        break
                if not skipp:
                    sl.append(Optional(ubb))
            elif isinstance(bgp, UnionBlock):
                pub = self.decomposeUnionBlock(bgp)
                if pub:
                    sl.append(pub)
            elif isinstance(bgp, JoinBlock):
                pub = self.decomposeJoinBlock(bgp)
                if pub:
                    sl.append(pub)

        if tl:
            if self.tempType == "METIS" or self.tempType == "SemEP":
                gs = self.decomposeForMETIS(tl)
            else:
                gs = self.decomposeBGP(tl)

            if gs:
                gs.extend(sl)
                sl = gs
            else:
                return None

        fl1 = self.includeFilter(sl, fl)
        fl = list(set(fl) - set(fl1))
        if sl:
            if len(sl) == 1 and isinstance(sl[0], UnionBlock) and fl != []:
                sl[0] = self.updateFilters(sl[0], fl)
            j = JoinBlock(sl, filters=fl)
            return j
        else:
            return None

    def decomposeForMETIS(self, tl):
        results = []
        stars = self.getQueryStar(tl)

        for s in stars:
            ltr = stars[s]
            mols = {}
            unions = {}
            for tp in ltr:
                if tp.predicate.constant:
                    p = utils.getUri(tp.predicate, self.prefixes)[1:-1]
                    t = self.config.findbypred(p)

                    if len(t) > 0:
                        if len(t) == 1:
                            for c in t:
                                if c in mols:
                                    mols[c].append(tp)
                                else:
                                    mols[c] = [tp]
                                break
                        else:
                            unions[tp] = t

                    else:
                        print("cannot find any matching cluster for:", tl)
                        return []
                else:
                    mm = [m for m in self.config.metadata]
                    unions[tp] = mm
            for m in mols:
                results.append(Service("<" + m + ">", mols[m]))

            for tp in unions.copy():
                cs = unions[tp]

                tps = [t for t in unions if t != tp and unions[t] == cs]
                if len(tps) > 0:
                    for u in tps:
                        del unions[u]
                tps.append(tp)
                samesource = None
                url = None
                differents = None
                for s in cs:
                    wr = self.config.findMolecule(s)
                    wrs = [w for w in wr['wrappers']]
                    wrr = wrs[0]['url']
                    if url is None or wrr == url:
                        url = wrr
                        samesource = s
                    else:
                        differents = s
                        break
                if differents is None:
                    results.append(Service("<" + samesource + ">", tps))
                else:
                    results.append(UnionBlock([UnionBlock([Service("<" + c + ">", tps)]) for c in cs]))

        return results

    def decomposeBGP(self, tl):
        stars = self.getQueryStar(tl)

        selectedmolecules = {}
        varpreds = {}
        starpreds = {}
        conn = self.getStarsConnections(stars)
        splitedstars = {}

        for s in stars.copy():
            ltr = stars[s]
            preds = [utils.getUri(tr.predicate, self.prefixes)[1:-1] for tr in ltr if tr.predicate.constant]
            starpreds[s] = preds
            typemols = self.checkRDFTypeStatemnt(ltr)
            if len(typemols) > 0:
                selectedmolecules[s] = typemols
                for m in typemols:
                    properties = [p['predicate'] for p in self.config.metadata[m]['predicates']]
                    pinter = set(properties).intersection(preds)
                    if len(pinter) != len(preds):
                        print("Subquery: ", stars[s], "\nCannot be executed, because it contains properties that "
                                                      "does not exist in this federations of datasets.")
                        return []
                continue

            if len(preds) == 0:
                found = False
                for v in conn.values():
                    if s in v:
                        mols = [m for m in self.config.metadata]
                        found = True
                if not found:
                    varpreds[s] = ltr
                    continue
            else:
                mols = self.config.findbypreds(preds)

            if len(mols) > 0:
                if s in selectedmolecules:
                    selectedmolecules[s].extend(mols)
                else:
                    selectedmolecules[s] = mols
            else:
                splitstars = self.config.find_preds_per_mt(preds)
                if len(splitstars) == 0:
                    print("cannot find any matching molecules for:", tl)
                    return []
                else:
                    splitedstars[s] = [stars[s], splitstars, preds]
                    for m in list(splitstars.keys()):
                        selectedmolecules[str(s+'_'+m)] = [m]
                    #return self.decomposeSplitedStar(stars[s], splitstars, preds)

        if len(varpreds) > 0:
            mols = [m for m in self.config.metadata]
            for s in varpreds:
                selectedmolecules[s] = mols

        molConn = self.getMTsConnection(selectedmolecules)
        results = []
        if len(splitedstars) > 0:
            for s in splitedstars:
                newstarpreds = {utils.getUri(tr.predicate, self.prefixes)[1:-1]: tr for tr in stars[s] if tr.predicate.constant}

                for m in splitedstars[s][1]:
                    stars[str(s + '_' + m)] = [newstarpreds[p] for p in splitedstars[s][1][m]]
                    starpreds[str(s + '_' + m)] = splitedstars[s][1][m]
                del stars[s]
                del starpreds[s]

        conn = self.getStarsConnections(stars)
        res = self.pruneMTs(conn, molConn, selectedmolecules, stars)
        # print(res)
        qpl0 = []
        qpl1 = []
        for s in res:
            if len(res[s]) == 1:
                if len(self.config.metadata[res[s][0]]['wrappers']) == 1:
                    endpoint = self.config.metadata[res[s][0]]['wrappers'][0]['url']
                    qpl0.append(Service("<" + endpoint + ">", list(set(stars[s]))))
                else:
                    sources = [w['url'] for w in self.config.metadata[res[s][0]]['wrappers']
                               if len(starpreds[s]) == len(list(set(starpreds[s]).intersection(set(w['predicates']))))]
                    # joins = [JoinBlock([Service("<" + url + ">", list(set(stars[s])))]) for url in sources]
                    # qpl1.append([UnionBlock([UnionBlock(joins)])])
                    if len(sources) == 1:
                        endpoint = sources[0]
                        qpl0.append(Service("<" + endpoint + ">", list(set(stars[s]))))
                    elif len(sources) > 1:
                        elems = [JoinBlock([Service("<" + ep + ">", list(set(stars[s])))]) for ep in sources]
                        ub = UnionBlock(elems)
                        qpl1.append(ub)
                    else:
                        # split and join
                        wpreds = {}

                        ptrs = {utils.getUri(tr.predicate, self.prefixes)[1:-1]: tr for tr in stars[s] if tr.predicate.constant}
                        for w in self.config.metadata[res[s][0]]['wrappers']:
                            wps = [p for p in w['predicates'] if p in starpreds[s]]
                            wpreds[w['url']] = wps

                        inall = []
                        difs = {}
                        for e in wpreds:
                            if len(inall) == 0:
                                inall = wpreds[e]
                            else:
                                inall = list(set(inall).intersection(wpreds[e]))

                            if e not in difs:
                                difs[e] = wpreds[e]
                            for d in difs:
                                if e == d:
                                    continue
                                dd = list(set(difs[d]).difference(wpreds[e]))
                                if len(dd) > 0:
                                    difs[d] = dd

                                dd = list(set(difs[e]).difference(wpreds[d]))
                                if len(dd) > 0:
                                    difs[e] = dd

                        oneone = {}
                        for e1 in wpreds:
                            for e2 in wpreds:
                                if e1 == e2 or e2 + '|-|' + e1 in oneone:
                                    continue
                                pp = set(wpreds[e1]).intersection(wpreds[e2])
                                pp = list(set(pp).difference(inall))
                                if len(pp) > 0:
                                    oneone[e1 + '|-|' + e2] = pp
                        onv = []
                        [onv.extend(d) for d in list(oneone.values())]
                        difv = []
                        [difv.extend(d) for d in list(difs.values())]
                        for o in onv:
                            if o in difv:
                                toremov = []
                                for d in difs:
                                    if o in difs[d]:
                                        difs[d].remove(o)
                                        difv.remove(o)
                                    if len(difs[d]) == 0:
                                        toremov.append(d)
                                for d in toremov:
                                    del difs[d]

                        ddd = onv + difv
                        rdftype = []
                        if len(set(inall + ddd)) == len(starpreds[s]):
                            if len(inall) > 0:
                                if len(inall) == 1 and inall[0] == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type':
                                    rdftype.extend(list(wpreds.keys()))
                                    pass
                                else:
                                    trps = [ptrs[p] for p in inall]
                                    elems = [JoinBlock([Service("<" + ep + ">", list(set(trps)))]) for ep in list(wpreds.keys())]
                                    ub = UnionBlock(elems)
                                    qpl1.append(ub)
                            if len(oneone) > 0:
                                for ee in oneone:
                                    e1, e2 = ee.split("|-|")
                                    pp = oneone[ee]
                                    if len(pp) == 1 and pp[0] == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type':
                                        rdftype.extend([e1, e2])
                                        pass
                                    else:
                                        trps = [ptrs[p] for p in pp]
                                        elems = [JoinBlock([Service("<" + e1 + ">", list(set(trps)))]),
                                                 JoinBlock([Service("<" + e2 + ">", list(set(trps)))])]
                                        ub = UnionBlock(elems)
                                        qpl1.append(ub)
                            if len(difs) > 0:
                                for d in difs:
                                    trps = [ptrs[p] for p in difs[d]]
                                    if d in rdftype:
                                        trps.append(ptrs['http://www.w3.org/1999/02/22-rdf-syntax-ns#type'])
                                    qpl0.append(Service("<" + d + ">", list(set(trps))))
                        else:
                            return []
            else:
                # preds = [utils.getUri(tr.predicate, self.prefixes)[1:-1] for tr in stars[s] if tr.predicate.constant]
                # mulres = self.decompose_multimolecule(res[s], stars[s], preds)
                # if isinstance(mulres, Service):
                #     results.append(mulres)
                # else:
                #     results.extend(mulres)

                md = self.metawrapperdecomposer(res[s], stars[s])
                if isinstance(md, Service):
                    qpl0.append(md)
                else:
                    for m in md:
                        if isinstance(m, Service):
                            qpl0.append(m)
                        else:
                            qpl1.append(m)
        if qpl0 and not self.joinlocally:
            joins = {}
            g = 0
            merged = []
            for i in range(len(qpl0)):
                if i+1 < len(qpl0):
                    for j in range(i+1, len(qpl0)):
                        s = qpl0[i]
                        k = qpl0[j]
                        if s.endpoint == k.endpoint:
                            if self.shareAtLeastOneVar(k.triples, s.triples):
                                if s.endpoint in joins:
                                    joins[s.endpoint].extend(s.triples + k.triples)
                                else:
                                    joins[s.endpoint] = s.triples + k.triples
                                merged.append(s)
                                merged.append(k)
                                joins[s.endpoint] = list(set(joins[s.endpoint]))

            [qpl0.remove(r) for r in set(merged)]
            for s in qpl0:
                if s.endpoint in joins:
                    if self.shareAtLeastOneVar(joins[s.endpoint], s.triples):
                        joins[s.endpoint].extend(s.triples)
                    else:

                        joins[s.endpoint + "|" + str(g)] = s.triples
                        g += 1
                else:
                    joins[s.endpoint] = s.triples

                joins[s.endpoint] = list(set(joins[s.endpoint]))

            qpl0 = []
            for e in joins:
                endp = e.split('|')[0]

                qpl0.append(Service('<' + endp + '>', joins[e]))

        if qpl0 and qpl1:
            qpl1.insert(0, qpl0)
            return qpl1
        elif qpl0 and not qpl1:
            return qpl0
        else:
            return qpl1

    def shareAtLeastOneVar(self, left, right):
        leftsubj = [s.subject.name for s in left if not s.subject.constant]
        leftobj = [s.theobject.name for s in left if not s.subject.constant]
        rightsubj = [s.subject.name for s in right if not s.subject.constant]
        rightobj = [s.theobject.name for s in right if not s.subject.constant]

        leftvars = leftsubj + leftobj
        rightvars = rightsubj + rightobj
        inter = set(leftvars).intersection(set(rightvars))
        # print (inter)
        if len(inter) > 0:
            return True

        return False

    def metawrapperdecomposer(self, res, triplepatterns):
        sourceindex = dict()
        urlmoleculemap = dict()
        predtrips = dict()
        preds = []
        for tr in triplepatterns:
            if tr.predicate.constant:
                p = utils.getUri(tr.predicate, self.prefixes)[1:-1]
                predtrips[p] = tr
                preds.append(p)
        for x in res:
            wrappers = self.config.metadata[x]
            wrappers = [w for w in wrappers['wrappers']]
            if len(wrappers) > 1:
                for w in wrappers:
                    exitsingpreds = []
                    for p in preds:
                        if p in w['predicates']:
                            exitsingpreds.append(predtrips[p])
                    if len(exitsingpreds) == 0:
                        continue
                    urlmoleculemap[w['url']] = x
                    if w['url'] not in sourceindex:
                        sourceindex[w['url']] = exitsingpreds
                    else:
                        sourceindex[w['url']].extend(exitsingpreds)
                        sourceindex[w['url']] = list(set(sourceindex[w['url']]))
            else:
                exitsingpreds = []
                w = wrappers[0]
                for p in preds:
                    if p in w['predicates']:
                        exitsingpreds.append(predtrips[p])
                if len(exitsingpreds) == 0:
                    continue

                urlmoleculemap[w['url']] = x
                if w['url'] not in sourceindex:
                    sourceindex[w['url']] = exitsingpreds
                else:
                    sourceindex[w['url']].extend(exitsingpreds)
                    sourceindex[w['url']] = list(set(sourceindex[w['url']]))

        if len(sourceindex) == 1:
            return Service('<' + list(sourceindex.keys())[0] + '>', list(set(triplepatterns)))

        # for url in sourceindex:
        #     eps = sourceindex[url]
        #     if len(eps) == len(triplepatterns):
        #         return Service('<' + url + '>', list(set(triplepatterns))) #urlmoleculemap[url]

        intersects = None
        for url in sourceindex:
            if intersects is None:
                intersects = set(sourceindex[url])
                continue
            intersects = intersects.intersection(set(sourceindex[url]))
            if len(intersects) == 0:
                break

        joins = []
        servs = []
        if intersects and len(intersects) > 0:
            singlesource = {url: sourceindex[url] for url in sourceindex if len(sourceindex[url]) == len(triplepatterns)}
            if len(singlesource) > 0:
                if len(singlesource) == 1:
                    for url in singlesource:
                        servs.append(Service("<" + url + ">", list(set(sourceindex[url]))))
                else:
                    for url in singlesource:
                        joins.append(JoinBlock([Service("<" + url + ">", list(set(sourceindex[url])))]))
            else:
                [sourceindex[url].remove(e) for e in intersects for url in sourceindex]
                ignore = []
                for url in sourceindex:
                    if len(sourceindex[url]) == len(triplepatterns):
                        servs.append(Service("<" + url + ">", list(set(sourceindex[url]))))
                        ignore.append(url)
                    else:
                        joins.append(JoinBlock([Service("<" + url + ">", list(intersects))]))
                for url in sourceindex:
                    if len(sourceindex[url]) > 0 and url not in ignore:
                        servs.append(Service("<" + url + ">", list(set(sourceindex[url]))))
            # if len(servs) == len(sourceindex):
            #     joins = servs
            #     servs = []
            # elif len(servs) == 1:
            #     joins = []
        else:
            #TODO: check other decompositions to make a true union
            joins.extend([JoinBlock([Service("<" + url + ">", triplepatterns)]) for url in sourceindex])

        if len(joins) > 0:
            servs.append(UnionBlock(joins))
        return servs

    def getMTsConnection(self, selectedmolecules):
        mcons = {}
        smolecules = [m for s in selectedmolecules for m in selectedmolecules[s]]
        for s in selectedmolecules:
            mols = selectedmolecules[s]
            for m in mols:
                mcons[m] = [n for n in self.config.metadata[m]['linkedTo'] if n in smolecules]
        return mcons

    def pruneMTs(self, conn, molConn, selectedmolecules, stars):
        newselected = {}
        res = {}
        for s in selectedmolecules:
            if len(selectedmolecules[s]) == 1:
                newselected[s] = list(selectedmolecules[s])
                res[s] = list(selectedmolecules[s])
            else:
                newselected[s] = []
                res[s] = []

        for s in selectedmolecules:
            sc = conn[s]
            for sm in selectedmolecules[s]:
                smolink = molConn[sm]
                for c in sc:
                    cmols = selectedmolecules[c]
                    nms = [m for m in smolink if m in cmols]
                    if len(nms) > 0:
                        res[s].append(sm)
                        res[c].extend(nms)
        #check predicate level connections
        newfilteredonly = {}
        for s in res:
            sc = [c for c in conn if s in conn[c]]
            for c in sc:
                connectingtp = [utils.getUri(tp.predicate, self.prefixes)[1:-1]
                         for tp in stars[c] if tp.theobject.name == s]
                connectingtp = list(set(connectingtp))
                sm = selectedmolecules[s]
                for m in sm:
                    srange = [p for r in self.config.metadata[m]['predicates'] for p in r['range'] if
                              r['predicate'] in connectingtp]
                    filteredmols = [r for r in res[s] if r in srange]
                    if len(filteredmols) > 0:
                        if s in newfilteredonly:
                            newfilteredonly[s].extend(filteredmols)
                        else:
                            res[s] = filteredmols

        for s in newfilteredonly:
            res[s] = list(set(newfilteredonly[s]))

        for s in res:
            if len(res[s]) == 0:
                res[s] = selectedmolecules[s]
            res[s] = list(set(res[s]))
        return res

    def checkRDFTypeStatemnt(self, ltr):
        types = self.getRDFTypeStatement(ltr)
        typemols = []
        for t in types:
            tt = utils.getUri(t.theobject, self.prefixes)[1:-1]
            if tt in self.config.metadata:
                typemols.append(tt)

        return typemols

    def getStarsConnections(self, stars):
        """
        extracts links between star-shaped sub-queries
        :param stars: map of star-shaped sub-queries with its root (subject) {subject: [triples in BGP]}
        :return: map of star-shaped sub-query root name (subject) with its connected sub-queries via its object node.
         {subj1: [subjn]} where one of subj1's triple pattern's object node is connected to subject node of subjn
        """
        conn = dict()
        for s in stars.copy():
            ltr = stars[s]
            conn[s] = []
            for c in stars:
                if c == s:
                    continue
                for t in ltr:
                    if t.theobject.name == c:
                        if c not in conn[s]:
                            conn[s].append(c)
                        break

        return conn
    '''
    ===================================================
    ========= STAR-SHAPED DECOMPOSITIONS ==============
    ===================================================
    '''
    def getQueryStar(self, tl):
        """
        extracts star-shaped subqueries from a list of triple patterns in a BGP
        :param tl: list of triple patterns in a BGP
        :return: map of star-shaped sub-queries with its root (subject) {subject: [triples in BGP]}
        """
        stars = dict()
        for t in tl:
            if t.subject.name in stars:
                stars[t.subject.name].append(t)
            else:
                stars[t.subject.name] = [t]
        return stars

    def getRDFTypeStatement(self, ltr):
        types = []
        for t in ltr:
            if t.predicate.constant \
                    and (t.predicate.name == "a"
                         or t.predicate.name == "rdf:type"
                         or t.predicate.name == "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>") \
                    and t.theobject.constant:
                types.append(t)

        return types

    '''
    ===================================================
    ========= FILTERS =================================
    ===================================================
    '''
    def includeFilter(self, jb_triples, fl):
        fl1 = []
        for jb in jb_triples:

            if isinstance(jb, list):
                for f in fl:
                    fl2 = self.includeFilterAux(f, jb)
                    fl1 = fl1 + fl2
            elif (isinstance(jb, UnionBlock)):
                for f in fl:
                    fl2 = self.includeFilterUnionBlock(jb, f)
                    fl1 = fl1 + fl2
            elif (isinstance(jb, Service)):
                for f in fl:
                    fl2 = self.includeFilterAuxSK(f, jb.triples, jb)
                    fl1 = fl1 + fl2
        return fl1

    def includeFilterAux(self, f, sl):
        fl1 = []
        for s in sl:
            vars_s = set()
            for t in s.triples:
                vars_s.update(set(utils.getVars(t)))
            vars_f = f.getVars()
            if set(vars_s) & set(vars_f) == set(vars_f):
                s.include_filter(f)
                fl1 = fl1 + [f]
        return fl1

    def includeFilterUnionBlock(self, jb, f):
        fl1 = []
        for jbJ in jb.triples:
            for jbUS in jbJ.triples:
                if isinstance(jbUS, Service):
                    vars_s = set(jbUS.getVars())
                    vars_f = f.getVars()
                    if set(vars_s) & set(vars_f) == set(vars_f):
                        jbUS.include_filter(f)
                        fl1 = fl1 + [f]
        return fl1

    def includeFilterAuxSK(self, f, sl, sr):
        """
        updated: includeFilterAuxS(f, sl, sr) below to include filters that all vars in filter exists in any of the triple
        patterns of a BGP. the previous impl includes them only if all vars are in a single triple pattern
        :param f:
        :param sl:
        :param sr:
        :return:
        """
        fl1 = []
        serviceFilter = False
        fvars = dict()
        vars_f = f.getVars()

        for v in vars_f:
            fvars[v] = False
        bgpvars = set()

        for s in sl:
            bgpvars.update(set(utils.getVars(s)))
            vars_s = set()
            if (isinstance(s, Triple)):
                vars_s.update(set(utils.getVars(s)))
            else:
                for t in s.triples:
                    vars_s.update(set(utils.getVars(t)))

            if set(vars_s) & set(vars_f) == set(vars_f):
                serviceFilter = True

        for v in bgpvars:
            if v in fvars:
                fvars[v] = True
        if serviceFilter:
            sr.include_filter(f)
            fl1 = fl1 + [f]
        else:
            fs = [v for v in fvars if not fvars[v]]
            if len(fs) == 0:
                sr.include_filter(f)
                fl1 = fl1 + [f]
        return fl1

    def updateFilters(self, node, filters):
        return UnionBlock(node.triples, filters)

    '''
    ===================================================
    ========= MAKE PLAN =================================
    ===================================================
    '''
    def makePlanQuery(self, q):
        x = self.makePlanUnionBlock(q.body)
        return x

    def makePlanUnionBlock(self, ub):
        r = []
        for jb in ub.triples:
            r.append(self.makePlanJoinBlock(jb))
        return UnionBlock(r, ub.filters)

    def makePlanJoinBlock(self, jb):
        sl = []
        ol = []

        for bgp in jb.triples:
            if type(bgp) == list:
                sl.extend(bgp)
            elif isinstance(bgp, Optional):

                for f in jb.filters:
                    vars_f = f.getVars()
                    if set(bgp.getVars()) & set(vars_f) == set(vars_f):
                        for t in bgp.bgg.triples:
                            if set(t.getVars()) & set(vars_f) == set(vars_f):
                                t.filters.extend(jb.filters)

                ol.append(Optional(self.makePlanUnionBlock(bgp.bgg)))
            elif isinstance(bgp, UnionBlock):

                for f in jb.filters:
                    vars_f = f.getVars()
                    if set(bgp.getVars()) & set(vars_f) == set(vars_f):
                        for t in bgp.triples:
                            if set(t.getVars()) & set(vars_f) == set(vars_f):
                                t.filters.extend(jb.filters)

                sl.append(self.makePlanUnionBlock(bgp))
            elif isinstance(bgp, JoinBlock):

                for f in jb.filters:
                    vars_f = f.getVars()
                    if set(bgp.getVars()) & set(vars_f) == set(vars_f):
                        bgp.filters.extend(jb.filters)

                sl.append(self.makePlanJoinBlock(bgp))
            elif isinstance(bgp, Service):

                for f in jb.filters:
                    vars_f = f.getVars()
                    if set(bgp.getVars()) & set(vars_f) == set(vars_f):
                        bgp.filters.extend(jb.filters)

                sl.append(bgp)

        pl = self.makePlanAux(sl, jb.filters)
        if ol:
            pl = [pl]
            pl.extend(ol)

        return JoinBlock(pl, filters=jb.filters)

    def makePlanAux(self, ls, filters=[]):
        return self.makeBushyTree(ls, filters)

    def makeBushyTree(self, ls, filters=[]):
        return Tree.makeBushyTree(ls, filters)

    def makeNaiveTree(self, ls):
        return Tree.makeNaiveTree(ls)

    def makeLeftLinealTree(self, ls):
        return Tree.makeLLTree(ls)

#
# if __name__ == '__main__':
#     from mulder.molecule.MTManager import Arango
#     for q in os.listdir("/home/kemele/git/Ontario/testqueries/bsbm/"):
#         print "============", q, "=================="
#         query = open("/home/kemele/git/Ontario/testqueries/bsbm/"+q).read()
#         config = Arango("/home/kemele/git/Ontario/config/bsbm.json")
#         dc = MediatorDecomposer(query, config)
#         print dc.decompose()
