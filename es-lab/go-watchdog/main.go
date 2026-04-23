// watchdog.go
//
// Small Go program that polls every Elasticsearch node listed in ES_NODES
// and logs state transitions:
//
//   * node UP   -> node DOWN     (failure)
//   * node DOWN -> node UP       (recovery)
//   * cluster status green/yellow/red transitions
//
// It also tells you which node is currently ACTIVE (first reachable in the
// list) — that's the simple client-side failover rule.
//
// To test:  docker compose up -d
//           docker logs -f watchdog
//           docker stop es02            # watch the logs react
//           docker start es02           # watch it recover
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

type nodeState struct {
	URL     string
	Up      bool
	Name    string
	LastErr string
}

type clusterHealth struct {
	Status           string `json:"status"`
	NumberOfNodes    int    `json:"number_of_nodes"`
	ActivePrimary    int    `json:"active_primary_shards"`
	ActiveShards     int    `json:"active_shards"`
	UnassignedShards int    `json:"unassigned_shards"`
}

var httpClient = &http.Client{Timeout: 2 * time.Second}

// probe a single node.  We hit /_cluster/health because it's cheap and it
// also tells us what the node thinks of the cluster.
func probe(url string) (nodeState, *clusterHealth) {
	st := nodeState{URL: url}

	resp, err := httpClient.Get(url + "/_cluster/health")
	if err != nil {
		st.LastErr = err.Error()
		return st, nil
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		st.LastErr = fmt.Sprintf("http %d", resp.StatusCode)
		return st, nil
	}

	var h clusterHealth
	if err := json.NewDecoder(resp.Body).Decode(&h); err != nil {
		st.LastErr = err.Error()
		return st, nil
	}

	// a 200 from /_cluster/health means the node is reachable AND in a cluster
	st.Up = true

	// fetch node name (nice for logs)
	if info, err := httpClient.Get(url + "/"); err == nil {
		defer info.Body.Close()
		var payload struct {
			Name string `json:"name"`
		}
		_ = json.NewDecoder(info.Body).Decode(&payload)
		st.Name = payload.Name
	}
	return st, &h
}

func main() {
	nodesEnv := os.Getenv("ES_NODES")
	if nodesEnv == "" {
		nodesEnv = "http://localhost:9200,http://localhost:9201"
	}
	nodes := strings.Split(nodesEnv, ",")

	pollSec := 3
	if v := os.Getenv("POLL_SECONDS"); v != "" {
		fmt.Sscanf(v, "%d", &pollSec)
	}

	log.Printf("watchdog starting — polling %d nodes every %ds", len(nodes), pollSec)

	// prior state, per URL
	prev := make(map[string]nodeState, len(nodes))
	for _, u := range nodes {
		prev[u] = nodeState{URL: u, Up: false}
	}
	prevClusterStatus := ""
	prevActiveURL := ""

	tick := time.NewTicker(time.Duration(pollSec) * time.Second)
	defer tick.Stop()

	for range tick.C {
		activeURL := ""                // first reachable node
		var activeHealth *clusterHealth

		for _, u := range nodes {
			curr, h := probe(u)
			before := prev[u]

			// transition detection
			switch {
			case !before.Up && curr.Up:
				log.Printf("✅ RECOVERED  %s (%s)", u, curr.Name)
			case before.Up && !curr.Up:
				log.Printf("❌ FAILED     %s  (%s)", u, curr.LastErr)
			}
			prev[u] = curr

			if curr.Up && activeURL == "" {
				activeURL = u
				activeHealth = h
			}
		}

		// failover event: the ACTIVE (first-reachable) node changed
		if activeURL != prevActiveURL {
			if prevActiveURL == "" {
				log.Printf("🎯 ACTIVE node is %s", activeURL)
			} else if activeURL == "" {
				log.Printf("💥 NO ACTIVE node — cluster unreachable")
			} else {
				log.Printf("🔁 FAILOVER  %s -> %s", prevActiveURL, activeURL)
			}
			prevActiveURL = activeURL
		}

		// cluster-status transitions (green/yellow/red)
		if activeHealth != nil {
			if activeHealth.Status != prevClusterStatus {
				log.Printf("🌡  cluster status: %s -> %s   (%d nodes, %d active / %d unassigned shards)",
					ifEmpty(prevClusterStatus, "unknown"),
					activeHealth.Status,
					activeHealth.NumberOfNodes,
					activeHealth.ActiveShards,
					activeHealth.UnassignedShards,
				)
				prevClusterStatus = activeHealth.Status
			}
		} else if prevClusterStatus != "red-unreachable" {
			log.Printf("🌡  cluster status: unreachable")
			prevClusterStatus = "red-unreachable"
		}
	}
}

func ifEmpty(s, def string) string {
	if s == "" {
		return def
	}
	return s
}
