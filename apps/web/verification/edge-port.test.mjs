import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createServer} from 'node:net'
import {createSocket} from 'node:dgram'
import {reserveEdgePort} from '../../../scripts/verification-edge-port.mjs'

const bind = (socket, port) => new Promise((resolve, reject) => {
  socket.once('error', reject); socket.bind(port, '127.0.0.1', resolve)
})
const close = socket => new Promise(resolve => socket.close(resolve))

test('selected edge port can bind both actual TCP and UDP listeners', async () => {
  const port = await reserveEdgePort(), tcp = createServer(), udp = createSocket('udp4')
  try {
    await new Promise((resolve, reject) => {tcp.once('error', reject); tcp.listen(port, '127.0.0.1', resolve)})
    await bind(udp, port)
    assert.equal(udp.address().port, tcp.address().port)
  } finally {await close(udp); if (tcp.listening) await close(tcp)}
})

test('occupied UDP candidate selects another port without disturbing its owner', async () => {
  const owner = createSocket('udp4')
  try {
    await bind(owner, 0)
    const occupied = owner.address().port
    const selected = await reserveEdgePort({port: occupied})
    assert.notEqual(selected, occupied)
    assert.equal(owner.address().port, occupied)
  } finally {await close(owner)}
})

test('exhausted UDP reservation refuses and leaves the original listener intact', async () => {
  const owner = createSocket('udp4')
  try {
    await bind(owner, 0)
    const occupied = owner.address().port
    await assert.rejects(reserveEdgePort({port: occupied, attempts: 1}),
      error => error.message === 'No usable TCP/UDP verification edge port' && error.cause.code === 'EADDRINUSE')
    assert.equal(owner.address().port, occupied)
  } finally {await close(owner)}
})
