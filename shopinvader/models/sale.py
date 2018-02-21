# -*- coding: utf-8 -*-
# Copyright 2017 Akretion (http://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import api, fields, models
from odoo.exceptions import UserError
import odoo.addons.decimal_precision as dp
import logging
from odoo.tools.translate import _
_logger = logging.getLogger(__name__)


class ShopinvaderCartStep(models.Model):
    _name = 'shopinvader.cart.step'
    _description = 'Shopinvader Cart Step'

    name = fields.Char(required=True)
    code = fields.Char(required=True)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    typology = fields.Selection([
        ('sale', 'Sale'),
        ('cart', 'Cart'),
        ], default='sale')
    shopinvader_backend_id = fields.Many2one(
        'locomotive.backend',
        'Backend')
    current_step_id = fields.Many2one(
        'shopinvader.cart.step',
        'Current Cart Step',
        readonly=True)
    done_step_ids = fields.Many2many(
        comodel_name='shopinvader.cart.step',
        string='Done Cart Step',
        readonly=True)
    # TODO move this in an extra OCA module
    shopinvader_state = fields.Selection([
        ('cancel', 'Cancel'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ], compute='_compute_shopinvader_state',
        store=True)

    def _get_shopinvader_state(self):
        self.ensure_one()
        if self.state == 'cancel':
            return 'cancel'
        elif self.state == 'done':
            return 'shipped'
        elif self.state == 'draft':
            return 'pending'
        else:
            return 'processing'

    @api.depends('state')
    def _compute_shopinvader_state(self):
        # simple way to have more human friendly name for
        # the sale order on the website
        for record in self:
            record.shopinvader_state = record._get_shopinvader_state()

    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res['shopinvader_backend_id'] = self.shopinvader_backend_id.id
        return res

    @api.multi
    def action_confirm_cart(self):
        for record in self:
            vals = {'typology': 'sale'}
            record.write(vals)
            if record.shopinvader_backend_id:
                record.shopinvader_backend_id._send_notification(
                    'cart_confirmation', record)
        return True

    @api.multi
    def action_button_confirm(self):
        res = super(SaleOrder, self).action_button_confirm()
        for record in self:
            if record.state != 'draft' and record.shopinvader_backend_id:
                record.shopinvader_backend_id._send_notification(
                    'sale_confirmation', record)
        return res

    def reset_cart_lines(self):
        for record in self:
            record.order_line.reset_price_tax()

    def _play_cart_onchange(self, vals):
        result = {}
        # TODO in 10 use and improve onchange helper module
        # TODO MIGRATE
        # if 'partner_id' in vals:
        #     res = self.onchange_partner_id(vals['partner_id']).get(
        #         'value', {})
        #     for key in ['pricelist_id', 'payment_term']:
        #         if key in res:
        #             result[key] = res[key]
        # if 'partner_shipping_id' in vals:
        #     res = self.onchange_delivery_id(
        #         self.company_id.id,
        #         vals.get('partner_id') or self.partner_id.id,
        #         vals['partner_shipping_id'], None).get('value', {})
        #     if 'fiscal_position' in res:
        #         result['fiscal_position'] = res['fiscal_position']
        return result

    def _need_to_reset_tax_price_on_line(self, vals):
        reset = False
        for field in ['fiscal_position', 'pricelist_id']:
            if field in vals and self[field].id != vals[field]:
                reset = True
        return reset

    @api.multi
    def write_with_onchange(self, vals):
        self.ensure_one()
        vals.update(self._play_cart_onchange(vals))
        reset = self._need_to_reset_tax_price_on_line(vals)
        self.write(vals)
        if reset:
            self.reset_cart_lines()
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    shopinvader_variant_id = fields.Many2one(
        'shopinvader.variant',
        compute='_compute_shopinvader_variant',
        string='Shopinvader Variant',
        store=True)

    def reset_price_tax(self):
        pass
        # TODO MIGRATE
        # for line in self:
        #     res = line.product_id_change(
        #         line.order_id.pricelist_id.id,
        #         line.product_id.id,
        #         qty=line.product_uom_qty,
        #         uom=line.product_uom.id,
        #         qty_uos=line.product_uos_qty,
        #         uos=line.product_uos.id,
        #         name=line.name,
        #         partner_id=line.order_id.partner_id.id,
        #         lang=False,
        #         update_tax=True,
        #         date_order=line.order_id.date_order,
        #         packaging=False,
        #         fiscal_position=line.order_id.fiscal_position.id,
        #         flag=True)['value']
        #     line.write({
        #         'price_unit': res['price_unit'],
        #         'discount': res.get('discount'),
        #         'tax_id': [(6, 0, res.get('tax_id', []))]
        #         })

    @api.depends('order_id.shopinvader_backend_id', 'product_id')
    def _compute_shopinvader_variant(self):
        for record in self:
            record.shopinvader_variant_id = self.env['shopinvader.variant']\
                .search([
                    ('record_id', '=', record.product_id.id),
                    ('shopinvader_product_id.backend_id', '=',
                        record.order_id.shopinvader_backend_id.id),
                    ])
