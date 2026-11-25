.pragma library

// The top-level widget and service entry points import this same file.
var publication = null
var listeners = new Set()

function notify() {
    for (var listener of Array.from(listeners))
        listener(publication ? publication.api : null)
}

function publish(api) {
    var token = { api: api }
    publication = token
    notify()
    return token
}

function clear(token) {
    // A replaced service can finish tearing down after its successor starts.
    if (!token || publication !== token) return
    publication = null
    notify()
}

function subscribe(listener) {
    listeners.add(listener)
    listener(publication ? publication.api : null)
    return function() { listeners.delete(listener) }
}
