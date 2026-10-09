import {createServer} from 'node:net'
import {createSocket} from 'node:dgram'

// Caddy serves TCP HTTPS and UDP QUIC on the same port. A TCP reservation
// alone can select a Windows port that is forbidden for UDP.
export async function reserveEdgePort({port = 0, attempts = 16} = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535 ||
      !Number.isInteger(attempts) || attempts < 1 || attempts > 64)
    throw new Error('Invalid verification edge port reservation')
  let last
  for (let attempt = 0; attempt < attempts; attempt++) {
    const tcp = createServer(), udp = createSocket('udp4')
    try {
      await new Promise((resolve, reject) => {
        tcp.once('error', reject)
        tcp.listen(attempt === 0 ? port : 0, '127.0.0.1', resolve)
      })
      const selected = tcp.address().port
      await new Promise((resolve, reject) => {
        udp.once('error', reject)
        udp.bind(selected, '127.0.0.1', resolve)
      })
      return selected
    } catch (error) {
      if (!['EACCES', 'EADDRINUSE'].includes(error.code)) throw error
      last = error
    } finally {
      await new Promise(resolve => {try {udp.close(resolve)} catch {resolve()}})
      if (tcp.listening) await new Promise(resolve => tcp.close(resolve))
    }
  }
  throw new Error('No usable TCP/UDP verification edge port', {cause: last})
}
