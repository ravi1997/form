import hashlib
from datetime import datetime, timezone
from bson import ObjectId

class GitVersionControl:
    @staticmethod
    def calculate_commit_hash(parent_hash, sections, message, author_id):
        """
        Generates a SHA-1 commit hash based on parent, sections schema, message, and author.
        """
        sha = hashlib.sha1()
        sha.update(str(parent_hash).encode('utf-8'))
        sha.update(str(sections).encode('utf-8'))
        sha.update(str(message).encode('utf-8'))
        sha.update(str(author_id).encode('utf-8'))
        sha.update(str(datetime.now(timezone.utc).timestamp()).encode('utf-8'))
        return sha.hexdigest()

    @staticmethod
    def create_commit(forms_col, form_id, branch_name, sections, message, author_id):
        """
        Creates a new commit on a branch.
        Updates the branch reference in the form document.
        """
        form = forms_col.find_one({"_id": form_id})
        if not form:
            return None, "Form not found"

        branches = form.get("vcs_branches", {})
        if not branches:
            branches = {"main": None}

        parent_hash = branches.get(branch_name)
        commit_hash = GitVersionControl.calculate_commit_hash(parent_hash, sections, message, author_id)

        commit_doc = {
            "form_id": form_id,
            "hash": commit_hash,
            "parent": parent_hash,
            "author_id": author_id,
            "message": message,
            "sections": sections,
            "timestamp": datetime.now(timezone.utc)
        }

        # Add commit to dedicated commits collection
        commits_col = forms_col.database["commits"]

        # Try using MongoDB session transaction (supported on Replica Sets)
        client = forms_col.database.client
        try:
            with client.start_session() as session:
                with session.start_transaction():
                    commits_col.insert_one(commit_doc, session=session)
                    res = forms_col.update_one(
                        {"_id": form_id},
                        {
                            "$set": {
                                f"vcs_branches.{branch_name}": commit_hash,
                                "updated_at": datetime.now(timezone.utc)
                            }
                        },
                        session=session
                    )
                    if res.matched_count == 0:
                        raise ValueError("Form not found during update")
            return commit_hash, None
        except Exception:
            # Fallback compensating strategy for standalone/non-replica-set deployments
            commits_col.insert_one(commit_doc)
            try:
                result = forms_col.update_one(
                    {"_id": form_id},
                    {
                        "$set": {
                            f"vcs_branches.{branch_name}": commit_hash,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )
                if result.matched_count == 0:
                    commits_col.delete_one({"hash": commit_hash})
                    return None, "Form not found"
            except Exception as e:
                commits_col.delete_one({"hash": commit_hash})
                raise e
            return commit_hash, None

    @staticmethod
    def create_branch(forms_col, form_id, new_branch, source_branch="main"):
        """
        Creates a new branch pointing to the same commit as source_branch.
        """
        form = forms_col.find_one({"_id": form_id})
        if not form:
            return False, "Form not found"

        branches = form.get("vcs_branches", {})
        if not branches or source_branch not in branches:
            return False, f"Source branch '{source_branch}' not found"

        if new_branch in branches:
            return False, f"Branch '{new_branch}' already exists"

        commit_hash = branches[source_branch]
        forms_col.update_one(
            {"_id": form_id},
            {"$set": {f"vcs_branches.{new_branch}": commit_hash, "updated_at": datetime.now(timezone.utc)}}
        )
        return True, None

    @staticmethod
    def get_diff(forms_col, form_id, from_ref, to_ref):
        """
        Compares two commits or branch heads and returns structural differences.
        """
        form = forms_col.find_one({"_id": form_id})
        if not form:
            return None, "Form not found"

        commits_col = forms_col.database["commits"]
        commits_cursor = commits_col.find({"form_id": form_id})
        commits = {c["hash"]: c for c in commits_cursor}
        branches = form.get("vcs_branches", {})

        # Resolve ref to commit hash
        from_hash = branches.get(from_ref, from_ref)
        to_hash = branches.get(to_ref, to_ref)

        from_commit = commits.get(from_hash)
        to_commit = commits.get(to_hash)

        if not from_commit and from_hash:
            return None, f"Ref '{from_ref}' not found"
        if not to_commit and to_hash:
            return None, f"Ref '{to_ref}' not found"

        from_sections = from_commit["sections"] if from_commit else []
        to_sections = to_commit["sections"] if to_commit else []

        # Simple question diff
        from_questions = {}
        for sec in from_sections:
            for q in sec.get("questions", []):
                from_questions[q["id"]] = q

        to_questions = {}
        for sec in to_sections:
            for q in sec.get("questions", []):
                to_questions[q["id"]] = q

        added = []
        removed = []
        modified = []

        for q_id, q in to_questions.items():
            if q_id not in from_questions:
                added.append(q)
            elif from_questions[q_id] != q:
                modified.append({
                    "id": q_id,
                    "before": from_questions[q_id],
                    "after": q
                })

        for q_id, q in from_questions.items():
            if q_id not in to_questions:
                removed.append(q)

        return {
            "from_ref": from_ref,
            "to_ref": to_ref,
            "diff": {
                "added": added,
                "removed": removed,
                "modified": modified
            }
        }, None

    @staticmethod
    def merge_branches(forms_col, form_id, source_branch, target_branch, author_id):
        """
        Merges source_branch into target_branch.
        Supports Fast-Forward and 3-way conflict-aware merge strategies.
        """
        form = forms_col.find_one({"_id": form_id})
        if not form:
            return None, "Form not found"

        branches = form.get("vcs_branches", {})
        if source_branch not in branches or target_branch not in branches:
            return None, "Source or target branch not found"

        source_hash = branches[source_branch]
        target_hash = branches[target_branch]

        if source_hash == target_hash:
            return {"merged": True, "message": "Already up to date"}, None

        commits_col = forms_col.database["commits"]
        commits_cursor = commits_col.find({"form_id": form_id})
        commits = {c["hash"]: c for c in commits_cursor}

        source_commit = commits.get(source_hash)
        target_commit = commits.get(target_hash)

        if not source_commit or not target_commit:
            return None, "Source or target commit history is empty"

        # Traversal to find Lowest Common Ancestor (LCA)
        def get_ancestors(commit_hash):
            ancestors = []
            curr = commit_hash
            while curr:
                ancestors.append(curr)
                c = commits.get(curr)
                curr = c["parent"] if c else None
            return ancestors

        src_ancestors = get_ancestors(source_hash)
        tgt_ancestors = get_ancestors(target_hash)

        common_ancestor = None
        for a in src_ancestors:
            if a in tgt_ancestors:
                common_ancestor = a
                break

        # Fast-Forward Merge
        if common_ancestor == target_hash:
            forms_col.update_one(
                {"_id": form_id},
                {"$set": {f"vcs_branches.{target_branch}": source_hash, "updated_at": datetime.now(timezone.utc)}}
            )
            return {"merged": True, "type": "fast_forward", "commit_hash": source_hash}, None

        # 3-Way Merge
        ancestor_commit = commits.get(common_ancestor)
        ancestor_sections = ancestor_commit["sections"] if ancestor_commit else []
        src_sections = source_commit["sections"]
        tgt_sections = target_commit["sections"]

        def map_questions(sections):
            res = {}
            for sec in sections:
                for q in sec.get("questions", []):
                    res[q["id"]] = q
            return res

        anc_qs = map_questions(ancestor_sections)
        src_qs = map_questions(src_sections)
        tgt_qs = map_questions(tgt_sections)

        merged_qs = {}
        conflicts = []

        all_ids = set(anc_qs.keys()) | set(src_qs.keys()) | set(tgt_qs.keys())

        for q_id in all_ids:
            in_anc = q_id in anc_qs
            in_src = q_id in src_qs
            in_tgt = q_id in tgt_qs

            if in_anc:
                src_val = src_qs.get(q_id)
                tgt_val = tgt_qs.get(q_id)
                anc_val = anc_qs.get(q_id)
                
                modified_src = in_src and src_val != anc_val
                modified_tgt = in_tgt and tgt_val != anc_val
                deleted_src = not in_src
                deleted_tgt = not in_tgt

                if deleted_src and deleted_tgt:
                    pass
                elif modified_src and modified_tgt:
                    if src_val == tgt_val:
                        merged_qs[q_id] = src_val
                    else:
                        merged_qs[q_id] = {
                            "id": q_id,
                            "type": "conflict",
                            "conflict_ours": tgt_val,
                            "conflict_theirs": src_val,
                            "conflict_ancestor": anc_val
                        }
                        conflicts.append(q_id)
                elif modified_src and deleted_tgt:
                    merged_qs[q_id] = {
                        "id": q_id,
                        "type": "conflict",
                        "conflict_ours": None,
                        "conflict_theirs": src_val,
                        "conflict_ancestor": anc_val
                    }
                    conflicts.append(q_id)
                elif modified_tgt and deleted_src:
                    merged_qs[q_id] = {
                        "id": q_id,
                        "type": "conflict",
                        "conflict_ours": tgt_val,
                        "conflict_theirs": None,
                        "conflict_ancestor": anc_val
                    }
                    conflicts.append(q_id)
                elif modified_src:
                    merged_qs[q_id] = src_val
                elif modified_tgt:
                    merged_qs[q_id] = tgt_val
                else:
                    if in_src and in_tgt:
                        merged_qs[q_id] = anc_val
            else:
                if in_src and in_tgt:
                    if src_qs[q_id] == tgt_qs[q_id]:
                        merged_qs[q_id] = src_qs[q_id]
                    else:
                        merged_qs[q_id] = {
                            "id": q_id,
                            "type": "conflict",
                            "conflict_ours": tgt_qs[q_id],
                            "conflict_theirs": src_qs[q_id],
                            "conflict_ancestor": None
                        }
                        conflicts.append(q_id)
                elif in_src:
                    merged_qs[q_id] = src_qs[q_id]
                elif in_tgt:
                    merged_qs[q_id] = tgt_qs[q_id]

        merged_sections = []
        for sec in src_sections:
            sec_copy = dict(sec)
            sec_qs = []
            for q in sec.get("questions", []):
                q_id = q["id"]
                if q_id in merged_qs:
                    sec_qs.append(merged_qs[q_id])
            sec_copy["questions"] = sec_qs
            merged_sections.append(sec_copy)

        merge_msg = f"Merge branch '{source_branch}' into '{target_branch}'"
        commit_hash, err = GitVersionControl.create_commit(
            forms_col, form_id, target_branch, merged_sections, merge_msg, author_id
        )

        return {
            "merged": True,
            "type": "3way",
            "commit_hash": commit_hash,
            "conflicts": conflicts
        }, None

    @staticmethod
    def purge_old_commits(forms_col, form_id=None):
        """
        Deletes commits older than 3 days that are not active/published.
        Active commits are defined as being targeted by any branch or tag of the form.
        Also skips commits where 'keep' is True.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        commits_col = forms_col.database["commits"]
        
        query = {"timestamp": {"$lt": cutoff}}
        if form_id:
            query["form_id"] = form_id
            
        old_commits = list(commits_col.find(query))
        if not old_commits:
            return 0
            
        deleted_count = 0
        for commit in old_commits:
            if commit.get("keep"):
                continue
                
            f_id = commit["form_id"]
            form = forms_col.find_one({"_id": f_id})
            if not form:
                commits_col.delete_one({"_id": commit["_id"]})
                deleted_count += 1
                continue
                
            branches = form.get("vcs_branches", {}).values()
            if commit["hash"] in branches:
                continue
                
            tags = [t["commit_hash"] for t in form.get("vcs_tags", [])]
            if commit["hash"] in tags:
                continue
                
            commits_col.delete_one({"_id": commit["_id"]})
            deleted_count += 1
            
        return deleted_count
